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


def within_posting_window(latest_event, now):
    """Validate event period and posting window. Returns True if OK to post."""
    start_at = time_utils.parse_jst_time(latest_event["StartAt"])
    end_at = time_utils.parse_jst_time(latest_event["EndAt"])

    if not (start_at <= now <= end_at):
        print("Current time is outside event period. Exiting.")
        return False

    posting_start = start_at + timedelta(hours=36.5)
    posting_end = end_at - timedelta(hours=2.5)
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


def _build_idol_rows(idol_id, expected_event_id, event_start_utc, now_utc,
                     stale_after=timedelta(hours=2)):
    """Read all borders for one idol and return (rows, latest_ok_timestamp).

    For each border the prediction file is classified:
      - missing, OR last-modified before the event start  -> insufficient
        data (the predictor couldn't produce a forecast yet); rendered as
        "データ不足".
      - last-modified after start but older than stale_after -> raises (the
        predictor should have refreshed; we want to be notified). Pass
        stale_after=None to disable this check (e.g. for offline previews).
      - fresh                                               -> used.

    expected_event_id may be None to skip the event-id match check.

    Every border always yields a row so the grid stays complete.
    latest_ok_timestamp is the newest Last-Modified among fresh files, or
    None if the idol has no fresh prediction.
    """
    rows = []
    latest_ok = None

    for border in ANNIVERSARY_BORDERS:
        path = f"prediction/{idol_id}/{float(border)}/predictions.json"
        pred, last_modified = r2.try_read_json_with_timestamp(path)

        if pred is None:
            rows.append({"border_label": f"{border}位", "insufficient": True})
            continue

        lm_utc = _to_utc(last_modified)
        if lm_utc < event_start_utc:
            # Data predates the event: predictor hasn't generated a forecast
            # for this idol/border yet (insufficient data).
            rows.append({"border_label": f"{border}位", "insufficient": True})
            continue

        if stale_after is not None and (now_utc - lm_utc) > stale_after:
            raise RuntimeError(
                f"Prediction for idol {idol_id} border {border} is stale: "
                f"last modified {last_modified} (after event start, older than {stale_after}). Path: {path}")

        event_id = pred["metadata"]["raw"]["id"]
        if expected_event_id is not None and event_id != expected_event_id:
            raise RuntimeError(
                f"Prediction for idol {idol_id} border {border} is for event {event_id}, "
                f"expected {expected_event_id}. Path: {path}")

        final_score = pred["data"]["raw"]["target"][-1]
        b75 = pred["data"]["raw"]["bounds"]["75"]
        b90 = pred["data"]["raw"]["bounds"]["90"]
        ci75 = (b75["lower_final"], b75["upper_final"])
        ci90 = (b90["lower_final"], b90["upper_final"])

        rows.append({
            "border_label": f"{border}位",
            "insufficient": False,
            "final": format_score_jp(final_score),
            "ci90": f"{format_score_jp(ci90[0])}〜{format_score_jp(ci90[1])}",
            "ci75": f"{format_score_jp(ci75[0])}〜{format_score_jp(ci75[1])}",
        })

        if latest_ok is None or lm_utc > latest_ok:
            latest_ok = lm_utc

    return rows, latest_ok


def gather_anniversary_rows(expected_event_id, event_start_utc, now_utc,
                            stale_after=timedelta(hours=2)):
    """Gather display rows for all 52 idols. Returns (idol_rows, latest_ts).

    Raises if no idol has any fresh prediction.
    """
    idol_rows = {}
    latest_ts = None
    for idol_id in range(1, 53):
        rows, latest_ok = _build_idol_rows(
            idol_id, expected_event_id, event_start_utc, now_utc, stale_after)
        idol_rows[idol_id] = rows
        if latest_ok and (latest_ts is None or latest_ok > latest_ts):
            latest_ts = latest_ok

    if latest_ts is None:
        raise RuntimeError("No fresh predictions found for any idol/border in this event.")

    return idol_rows, latest_ts


def render_anniversary_images(event_name, pred_time_str, idol_rows, out_dir):
    """Render one PNG per idol group. Returns the list of image paths."""
    from utils import html_renderer

    os.makedirs(out_dir, exist_ok=True)
    image_paths = []
    for group in idol_config.IDOL_GROUPS:
        accent = idol_config.GROUP_COLORS.get(group["key"], "#2980b9")
        idols = [idol_config.build_idol_render(idol_id, idol_rows[idol_id])
                 for idol_id in group["members"]]

        image_path = os.path.join(out_dir, f"summary_{group['key']}.png")
        html_renderer.render_group_image(
            group_name=group["name"],
            accent=accent,
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

    idol_rows, latest_ts = gather_anniversary_rows(expected_event_id, event_start_utc, now_utc)
    pred_time_str = format_pred_time(latest_ts)

    image_paths = render_anniversary_images(event_name, pred_time_str, idol_rows, out_dir)

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
    if not within_posting_window(latest_event, now):
        return

    if event_type == ANNIVERSARY_EVENT_TYPE:
        run_anniversary_event(latest_event, now, twitter_client, twitter_api_v1, debug_mode)
    else:
        run_normal_event(latest_event, now, twitter_client, twitter_api_v1, debug_mode)


if __name__ == "__main__":
    main()
