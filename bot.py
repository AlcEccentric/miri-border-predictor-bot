import sys
import os
import tweepy
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
from utils import r2, time_utils

BORDER_FILES = {
    100: "prediction/0/100.0/predictions.json",
    2500: "prediction/0/2500.0/predictions.json"
}

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

def setup_twitter_api():
    """Setup Twitter API client using environment variables"""
    try:
        # Load .env file
        load_dotenv()

        # Twitter API v2 credentials
        bearer_token = os.getenv('TWITTER_BEARER_TOKEN')
        consumer_key = os.getenv('TWITTER_CONSUMER_KEY')
        consumer_secret = os.getenv('TWITTER_CONSUMER_SECRET')
        access_token = os.getenv('TWITTER_ACCESS_TOKEN')
        access_token_secret = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')

        if not all([bearer_token, consumer_key, consumer_secret, access_token, access_token_secret]):
            raise ValueError("Missing Twitter API credentials in environment variables")

        # Create API client for v2 (for posting tweets)
        client = tweepy.Client(
            bearer_token=bearer_token,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
            wait_on_rate_limit=True
        )

        return client
    except Exception as e:
        print(f"Error setting up Twitter API: {e}")
        return None

def post_to_twitter(client, tweet_text, debug_mode=False):
    """Post text-only tweet to Twitter"""
    if debug_mode:
        print(f"DEBUG MODE: Would post tweet:\n{tweet_text}")
        return

    try:
        response = client.create_tweet(text=tweet_text)

        tweet_id = response.data['id']
        tweet_url = f"https://twitter.com/i/web/status/{tweet_id}"
        print(f"Tweet posted successfully!")
        print(f"Tweet ID: {tweet_id}")
        print(f"Tweet URL: {tweet_url}")
        return response
    except Exception as e:
        print(f"Error posting to Twitter: {e}")
        raise

def main():
    # Check for debug mode
    debug_mode = '--debug' in sys.argv or os.getenv('DEBUG_MODE', '').lower() == 'true'

    if debug_mode:
        print("Running in DEBUG MODE, meaning no tweets will be posted.")

    # Setup Twitter API (skip if in debug mode)
    twitter_client = None
    if not debug_mode:
        twitter_client = setup_twitter_api()
        if not twitter_client:
            print("Failed to setup Twitter API. Exiting.")
            return

    # 1. Load latest event info
    latest_event = r2.read_json_file("metadata/latest_event_border_info.json")

    # Event name used in tweets
    event_name = latest_event.get("EventName", "")

    if latest_event["EventType"] not in [3, 4, 11, 13]:
        print("EventType not eligible. Exiting.")
        return

    now = time_utils.now_jst()
    start_at = time_utils.parse_jst_time(latest_event["StartAt"])
    end_at = time_utils.parse_jst_time(latest_event["EndAt"])

    if not (start_at <= now <= end_at):
        print("Current time is outside event period. Exiting.")
        return

    # Check if current time is within the posting window [start_at + 36.5hr, end_at - 2.5hr]
    posting_start = start_at + timedelta(hours=36.5)
    posting_end = end_at - timedelta(hours=2.5)

    if not (posting_start <= now <= posting_end):
        print(f"Current time {now} is outside posting window [{posting_start} - {posting_end}]. Exiting.")
        return

    # 2. Collect prediction data for all borders
    border_predictions = {}
    prediction_timestamp = None

    for border, path in BORDER_FILES.items():
        pred = r2.read_json_file(path)

        # Check EventId
        if pred["metadata"]["raw"]["id"] != latest_event["EventId"]:
            raise Exception(f"Prediction for event {latest_event['EventId']} not available for border {border}")

        # Get prediction file timestamp from R2 (use the first one we encounter)
        if prediction_timestamp is None:
            prediction_timestamp = r2.get_file_timestamp(path)
            print(f"DEBUG: Raw prediction timestamp for border {border}: {prediction_timestamp}")
            print(f"DEBUG: Timestamp type: {type(prediction_timestamp)}")

            # Check if prediction data is stale (more than 2 hours old)
            if isinstance(prediction_timestamp, datetime):
                if prediction_timestamp.tzinfo is None:
                    pred_utc = pytz.utc.localize(prediction_timestamp)
                else:
                    pred_utc = prediction_timestamp.astimezone(pytz.utc)

                now_utc = now.astimezone(pytz.utc)
                time_diff = now_utc - pred_utc

                if time_diff > timedelta(hours=2):
                    print(f"Prediction data is stale. Generated {time_diff} ago (more than 2 hours). Exiting.")
                    return

        final_score = pred["data"]["raw"]["target"][-1]
        ci_90 = (pred["data"]["raw"]["bounds"]["90"]["lower"][-1],
                 pred["data"]["raw"]["bounds"]["90"]["upper"][-1])
        ci_75 = (pred["data"]["raw"]["bounds"]["75"]["lower"][-1],
                 pred["data"]["raw"]["bounds"]["75"]["upper"][-1])

        # Store prediction data
        border_predictions[border] = {
            'final_score': final_score,
            'ci_90': ci_90,
            'ci_75': ci_75
        }

    # 3. Create tweet text with all predictions
    # Format prediction timestamp for display
    if isinstance(prediction_timestamp, datetime):
        if prediction_timestamp.tzinfo is None:
            utc_timestamp = pytz.utc.localize(prediction_timestamp)
        else:
            utc_timestamp = prediction_timestamp.astimezone(pytz.utc)

        jst = pytz.timezone('Asia/Tokyo')
        jst_timestamp = utc_timestamp.astimezone(jst)
        pred_time_str = jst_timestamp.strftime("%Y-%m-%d %H:%M JST")
    else:
        pred_time_str = str(prediction_timestamp)

    tweet_text = f"{event_name}\n\n"
    tweet_text += f"予測生成日時：{pred_time_str}\n\n"

    # Add predictions for each border with confidence intervals (indented format)
    for border in sorted(BORDER_FILES.keys()):
        if border in border_predictions:
            final_score = border_predictions[border]['final_score']
            ci_90 = border_predictions[border]['ci_90']
            ci_75 = border_predictions[border]['ci_75']

            tweet_text += f"- {border}位予測値：{format_score_jp(final_score)}\n"
            tweet_text += f"  - 90%CI：{format_score_jp(ci_90[0])}-{format_score_jp(ci_90[1])}\n"
            tweet_text += f"  - 75%CI：{format_score_jp(ci_75[0])}-{format_score_jp(ci_75[1])}\n"
            tweet_text += "\n"

    # Add footnote
    tweet_text += "※CI: 信頼区間"

    # 4. Post tweet
    try:
        post_to_twitter(twitter_client, tweet_text, debug_mode)
        if not debug_mode:
            print("Tweet posted successfully with predictions for all borders!")
    except Exception as e:
        print(f"Failed to post tweet: {e}")

if __name__ == "__main__":
    main()
