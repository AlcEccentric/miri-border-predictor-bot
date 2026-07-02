import sys
import os
import tweepy
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
from utils import r2, time_utils
from utils import idol_config

# Normal events: single idol_id 0, borders 100 / 2500.
NORMAL_BORDER_FILES = {
    100: "prediction/0/100.0/predictions.json",
    2500: "prediction/0/2500.0/predictions.json",
}
NORMAL_EVENT_TYPES = [3, 4, 11, 13]

# Type 5 (anniversary) events: idol_id 1..52, borders 100 / 1000.
ANNIVERSARY_EVENT_TYPE = 5
ANNIVERSARY_BORDERS = [100, 1000]

WEBSITE_URL = "https://yuenimillion.live"

# How long after the event start before the bot begins posting. Anniversary
# events warm up more slowly, so they hold off longer.
NORMAL_POSTING_START_OFFSET = timedelta(hours=36.5)
ANNIVERSARY_POSTING_START_OFFSET = timedelta(hours=72)
# Stop posting this long before the event ends.
POSTING_END_OFFSET = timedelta(hours=2.5)

# A prediction file that belongs to the current event but hasn't been
# refreshed within this window is "stale": still rendered, but flagged.
# 3h is chosen because data refreshes ~hourly and CDN/caching can add ~1h,
# so ~2h-old data is normal; 3h avoids false positives.
STALE_AFTER = timedelta(hours=3)

# Per-border freshness classification outcomes.
STATE_FRESH = "fresh"
STATE_STALE = "stale"
STATE_INSUFFICIENT = "insufficient"


def format_score_jp(score):
    """Format score in Japanese units (万 only for 10000+)"""
    if score >= 10000:  # 万 (ten thousand)
        man_value = score / 10000
        if man_value == int(man_value):
            return f"{int(man_value)}万"
        else:
            return f"{man_value:.1f}万"
    else:
        return f"{score:,}"


def format_pred_time(prediction_timestamp):
    """Format an R2 LastModified timestamp as JST display string."""
    if isinstance(prediction_timestamp, datetime):
        if prediction_timestamp.tzinfo is None:
            utc_timestamp = pytz.utc.localize(prediction_timestamp)
        else:
            utc_timestamp = prediction_timestamp.astimezone(pytz.utc)
        jst = pytz.timezone('Asia/Tokyo')
        return utc_timestamp.astimezone(jst).strftime("%Y-%m-%d %H:%M JST")
    return str(prediction_timestamp)


def ensure_not_stale(prediction_timestamp, now):
    """Raise if the prediction is more than 2 hours old."""
    if not isinstance(prediction_timestamp, datetime):
        raise RuntimeError(f"Unexpected prediction timestamp type: {type(prediction_timestamp)}")
    if prediction_timestamp.tzinfo is None:
        pred_utc = pytz.utc.localize(prediction_timestamp)
    else:
        pred_utc = prediction_timestamp.astimezone(pytz.utc)
    age = now.astimezone(pytz.utc) - pred_utc
    if age > timedelta(hours=2):
        raise RuntimeError(f"Prediction data is stale: generated {age} ago (more than 2 hours).")


def setup_twitter_api():
    """Setup Twitter API clients (v2 for posting, v1.1 for media upload)."""
    load_dotenv()

    bearer_token = os.getenv('TWITTER_BEARER_TOKEN')
    consumer_key = os.getenv('TWITTER_CONSUMER_KEY')
    consumer_secret = os.getenv('TWITTER_CONSUMER_SECRET')
    access_token = os.getenv('TWITTER_ACCESS_TOKEN')
    access_token_secret = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')

    if not all([bearer_token, consumer_key, consumer_secret, access_token, access_token_secret]):
        raise ValueError("Missing Twitter API credentials in environment variables")

    client = tweepy.Client(
        bearer_token=bearer_token,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
        wait_on_rate_limit=True
    )

    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_token_secret)
    api_v1 = tweepy.API(auth, wait_on_rate_limit=True)

    return client, api_v1


def post_tweet(client, api_v1, tweet_text, image_paths=None, debug_mode=False):
    """Post a tweet, optionally with images."""
    image_paths = image_paths or []

    if debug_mode:
        print(f"DEBUG MODE: Would post tweet:\n{tweet_text}")
        if image_paths:
            print(f"DEBUG MODE: Would attach images: {image_paths}")
        return

    try:
        media_ids = []
        for image_path in image_paths:
            media = api_v1.media_upload(image_path)
            media_ids.append(media.media_id)
            print(f"Uploaded media: {image_path}")

        kwargs = {"text": tweet_text}
        if media_ids:
            kwargs["media_ids"] = media_ids
        response = client.create_tweet(**kwargs)

        tweet_id = response.data['id']
        print(f"Tweet posted successfully! ID: {tweet_id}")
        print(f"Tweet URL: https://twitter.com/i/web/status/{tweet_id}")
        return response
    except Exception as e:
        print(f"Error posting to Twitter: {e}")
        raise


def within_posting_window(latest_event, now, start_offset):
    """Validate event period and posting window. Returns True if OK to post.

    start_offset is how long after the event start posting may begin (it
    differs by event type).
    """
    start_at = time_utils.parse_jst_time(latest_event["StartAt"])
    end_at = time_utils.parse_jst_time(latest_event["EndAt"])

    if not (start_at <= now <= end_at):
        print("Current time is outside event period. Exiting.")
        return False

    posting_start = start_at + start_offset
    posting_end = end_at - POSTING_END_OFFSET
    if not (posting_start <= now <= posting_end):
        print(f"Current time {now} is outside posting window [{posting_start} - {posting_end}]. Exiting.")
        return False

    return True


def run_normal_event(latest_event, now, client, api_v1, debug_mode):
    """Text-only prediction post for normal events (idol_id 0)."""
    event_name = latest_event["EventName"]
    border_predictions = {}
    prediction_timestamp = None

    for border, path in NORMAL_BORDER_FILES.items():
        pred = r2.read_json_file(path)

        if pred["metadata"]["raw"]["id"] != latest_event["EventId"]:
            raise Exception(f"Prediction for event {latest_event['EventId']} not available for border {border}")

        if prediction_timestamp is None:
            prediction_timestamp = r2.get_file_timestamp(path)
            ensure_not_stale(prediction_timestamp, now)

        final_score = pred["data"]["raw"]["target"][-1]
        ci_90 = (pred["data"]["raw"]["bounds"]["90"]["lower"][-1],
                 pred["data"]["raw"]["bounds"]["90"]["upper"][-1])
        ci_75 = (pred["data"]["raw"]["bounds"]["75"]["lower"][-1],
                 pred["data"]["raw"]["bounds"]["75"]["upper"][-1])

        border_predictions[border] = {'final_score': final_score, 'ci_90': ci_90, 'ci_75': ci_75}

    pred_time_str = format_pred_time(prediction_timestamp)
    tweet_text = f"{event_name}\n\n予測生成日時：{pred_time_str}\n\n"

    for border in sorted(NORMAL_BORDER_FILES.keys()):
        if border in border_predictions:
            bp = border_predictions[border]
            tweet_text += f"- {border}位予測値：{format_score_jp(bp['final_score'])}\n"
            tweet_text += f"  - 90%CI：{format_score_jp(bp['ci_90'][0])}-{format_score_jp(bp['ci_90'][1])}\n"
            tweet_text += f"  - 75%CI：{format_score_jp(bp['ci_75'][0])}-{format_score_jp(bp['ci_75'][1])}\n\n"

    tweet_text += "※CI: 信頼区間"

    post_tweet(client, api_v1, tweet_text, debug_mode=debug_mode)


def _to_utc(dt):
    if dt.tzinfo is None:
        return pytz.utc.localize(dt)
    return dt.astimezone(pytz.utc)


def _classify_timestamp(last_modified, event_start_utc, now_utc):
    """Classify a prediction file's freshness from its Last-Modified time.

    event_start_utc == None disables the check (demo/test mode) -> FRESH.
    Returns one of STATE_FRESH / STATE_STALE / STATE_INSUFFICIENT.
    (404 / retrieval errors are handled by the caller, not here.)
    """
    if event_start_utc is None:
        return STATE_FRESH

    lm_utc = _to_utc(last_modified)
    if lm_utc < event_start_utc:
        # Leftover file from a previous event: no forecast for this event yet.
        return STATE_INSUFFICIENT
    if lm_utc < now_utc - STALE_AFTER:
        return STATE_STALE
    return STATE_FRESH


def _build_idol_rows(idol_id, expected_event_id, event_start_utc, now_utc):
    """Read all borders for one idol.

    Returns (rows, latest_shown_ts):
      - rows: one display dict per border. Fresh borders show the numbers;
        insufficient borders are marked "データ不足".
      - latest_shown_ts: newest Last-Modified among fresh borders, or None.

    Per-border classification (order matters):
      1. Retrieval error (network / non-404 HTTP / 200 without a usable
         Last-Modified) -> raises (fail-closed: never show unverifiable data).
      2. Missing (404), OR Last-Modified before event start -> insufficient
         (leftover file from a previous event) -> "データ不足".
      3. eventStart <= Last-Modified < now - 3h -> STALE -> raises, aborting
         the whole post (the predictor should have refreshed by now).
      4. Fresh -> shown. A fresh file that still lacks bounds means the
         predictor couldn't produce a full forecast -> treated as
         insufficient ("データ不足"). Malformed bounds -> raises.

    expected_event_id may be None to skip the event-id match check.
    """
    rows = []
    latest_shown = None

    for border in ANNIVERSARY_BORDERS:
        path = f"prediction/{idol_id}/{float(border)}/predictions.json"
        # A network error or non-404 HTTP error propagates out of this call.
        pred, last_modified = r2.try_read_json_with_timestamp(path)

        if pred is None:
            # 404: file doesn't exist -> insufficient data for this border.
            rows.append({"border_label": f"{border}位", "insufficient": True})
            continue

        # Integrity: we got data but can't verify its age -> fail-closed.
        if event_start_utc is not None and not isinstance(last_modified, datetime):
            raise RuntimeError(
                f"Prediction for idol {idol_id} border {border} has no usable "
                f"Last-Modified; cannot verify freshness. Path: {path}")

        state = _classify_timestamp(last_modified, event_start_utc, now_utc)

        if state == STATE_INSUFFICIENT:
            rows.append({"border_label": f"{border}位", "insufficient": True})
            continue

        if state == STATE_STALE:
            # Belongs to this event but not refreshed within STALE_AFTER.
            # Abort the entire post so we get notified rather than tweeting
            # partially outdated numbers.
            raise RuntimeError(
                f"Prediction for idol {idol_id} border {border} is stale: "
                f"last modified {last_modified} (older than {STALE_AFTER} before now). "
                f"Aborting post. Path: {path}")

        # Fresh: this file should belong to the current event.
        event_id = pred["metadata"]["raw"]["id"]
        if expected_event_id is not None and event_id != expected_event_id:
            raise RuntimeError(
                f"Prediction for idol {idol_id} border {border} is for event {event_id}, "
                f"expected {expected_event_id}. Path: {path}")

        # Bounds may be absent: the predictor couldn't produce a full forecast
        # (insufficient data) even though a point value exists -> データ不足.
        # Present-but-malformed bounds is an integrity error -> raise.
        bounds = pred["data"]["raw"].get("bounds")
        if not bounds:
            rows.append({"border_label": f"{border}位", "insufficient": True})
            continue
        try:
            ci75 = (bounds["75"]["lower_final"], bounds["75"]["upper_final"])
            ci90 = (bounds["90"]["lower_final"], bounds["90"]["upper_final"])
        except (KeyError, TypeError) as e:
            raise RuntimeError(
                f"Prediction for idol {idol_id} border {border} has malformed bounds "
                f"({e}). Path: {path}")

        final_score = pred["data"]["raw"]["target"][-1]
        rows.append({
            "border_label": f"{border}位",
            "insufficient": False,
            "final": format_score_jp(final_score),
            "ci90": f"{format_score_jp(ci90[0])}〜{format_score_jp(ci90[1])}",
            "ci75": f"{format_score_jp(ci75[0])}〜{format_score_jp(ci75[1])}",
        })

        lm_utc = _to_utc(last_modified)
        if latest_shown is None or lm_utc > latest_shown:
            latest_shown = lm_utc

    return rows, latest_shown


def gather_anniversary_rows(expected_event_id, event_start_utc, now_utc):
    """Gather display data for all 52 idols.

    Returns (idol_rows, latest_ts). Raises on any stale border, or if no
    idol has any fresh border at all.
    """
    idol_rows = {}
    latest_ts = None
    for idol_id in range(1, 53):
        rows, latest_shown = _build_idol_rows(
            idol_id, expected_event_id, event_start_utc, now_utc)
        idol_rows[idol_id] = rows
        if latest_shown and (latest_ts is None or latest_shown > latest_ts):
            latest_ts = latest_shown

    if latest_ts is None:
        raise RuntimeError("No fresh predictions found for any idol/border in this event.")

    return idol_rows, latest_ts


def render_anniversary_images(event_name, pred_time_str, idol_rows, out_dir):
    """Render one PNG per idol group. Returns the list of image paths."""
    from utils import html_renderer

    os.makedirs(out_dir, exist_ok=True)
    image_paths = []
    for group in idol_config.IDOL_GROUPS:
        theme = idol_config.group_theme(group["key"])
        idols = [idol_config.build_idol_render(idol_id, idol_rows[idol_id])
                 for idol_id in group["members"]]

        image_path = os.path.join(out_dir, f"summary_{group['key']}.png")
        html_renderer.render_group_image(
            group_name=group["name"],
            theme=theme,
            event_name=event_name,
            pred_time=pred_time_str,
            idols=idols,
            output_path=image_path,
        )
        print(f"Generated image for group {group['name']}: {image_path}")
        image_paths.append(image_path)
    return image_paths


def build_anniversary_tweet_text(event_name, pred_time_str):
    """Compose the tweet body for a type 5 (anniversary) event."""
    border_text = "・".join(f"{b}位" for b in ANNIVERSARY_BORDERS)
    return (
        f"{event_name}\n\n"
        f"各アイドルの{border_text}ボーダー予測（最終スコア・90%/75%CI）です。\n"
        f"予測更新日時：{pred_time_str}\n\n"
        f"サイトはこちら：{WEBSITE_URL}\n\n"
        "※CI: 信頼区間"
    )


def run_anniversary_event(latest_event, now, client, api_v1, debug_mode):
    """Render and post 4 group images (52 idols) for type 5 events."""
    event_name = latest_event["EventName"]
    expected_event_id = latest_event["EventId"]
    event_start_utc = _to_utc(time_utils.parse_jst_time(latest_event["StartAt"]))
    now_utc = now.astimezone(pytz.utc)

    out_dir = "debug" if debug_mode else "output"

    idol_rows, latest_ts = gather_anniversary_rows(
        expected_event_id, event_start_utc, now_utc)
    pred_time_str = format_pred_time(latest_ts)

    image_paths = render_anniversary_images(
        event_name, pred_time_str, idol_rows, out_dir)

    tweet_text = build_anniversary_tweet_text(event_name, pred_time_str)

    try:
        post_tweet(client, api_v1, tweet_text, image_paths=image_paths, debug_mode=debug_mode)
        if not debug_mode:
            print("Tweet posted successfully with anniversary group images!")
    finally:
        if not debug_mode:
            for image_path in image_paths:
                try:
                    os.remove(image_path)
                    print(f"Cleaned up image file: {image_path}")
                except OSError:
                    pass


def main():
    debug_mode = '--debug' in sys.argv or os.getenv('DEBUG_MODE', '').lower() == 'true'
    if debug_mode:
        print("Running in DEBUG MODE, meaning no tweets will be posted.")

    twitter_client = None
    twitter_api_v1 = None
    if not debug_mode:
        twitter_client, twitter_api_v1 = setup_twitter_api()

    latest_event = r2.read_json_file("metadata/latest_event_border_info.json")
    event_type = latest_event["EventType"]

    if event_type not in NORMAL_EVENT_TYPES and event_type != ANNIVERSARY_EVENT_TYPE:
        print("EventType not eligible. Exiting.")
        return

    now = time_utils.now_jst()
    if event_type == ANNIVERSARY_EVENT_TYPE:
        start_offset = ANNIVERSARY_POSTING_START_OFFSET
    else:
        start_offset = NORMAL_POSTING_START_OFFSET
    if not within_posting_window(latest_event, now, start_offset):
        return

    if event_type == ANNIVERSARY_EVENT_TYPE:
        run_anniversary_event(latest_event, now, twitter_client, twitter_api_v1, debug_mode)
    else:
        run_normal_event(latest_event, now, twitter_client, twitter_api_v1, debug_mode)


if __name__ == "__main__":
    main()
