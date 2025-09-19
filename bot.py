import sys
import os
import tweepy
from datetime import datetime
import pytz
from dotenv import load_dotenv
from utils import r2, time_utils, image_generator

BORDER_FILES = {
    100: "prediction/0/100.0/predictions.json",
    2500: "prediction/0/2500.0/predictions.json"
}

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
        
        # Create API client for v2 (for posting tweets) - matching working test configuration
        client = tweepy.Client(
            bearer_token=bearer_token,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
            wait_on_rate_limit=True
        )
        
        # Create API v1.1 client for media upload
        auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
        auth.set_access_token(access_token, access_token_secret)
        api_v1 = tweepy.API(auth, wait_on_rate_limit=True)
        
        return client, api_v1
    except Exception as e:
        print(f"Error setting up Twitter API: {e}")
        return None, None

def post_to_twitter(client, api_v1, image_paths, tweet_text, debug_mode=False):
    """Post tweet with multiple images to Twitter"""
    if debug_mode:
        print(f"DEBUG MODE: Would post tweet: {tweet_text}")
        print(f"DEBUG MODE: Would attach images: {image_paths}")
        return
    
    try:
        # Upload all media using API v1.1
        media_ids = []
        for image_path in image_paths:
            media = api_v1.media_upload(image_path)
            media_ids.append(media.media_id)
            print(f"Uploaded media: {image_path}")
        
        # Post tweet with all media using API v2
        response = client.create_tweet(
            text=tweet_text,
            media_ids=media_ids
        )
        
        tweet_id = response.data['id']
        tweet_url = f"https://twitter.com/i/web/status/{tweet_id}"
        print(f"Tweet posted successfully with {len(media_ids)} images!")
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
        print("Running in DEBUG MODE")
        # Create debug directory if it doesn't exist
        os.makedirs('debug', exist_ok=True)
    else:
        # Create output directory if it doesn't exist
        os.makedirs('output', exist_ok=True)
    
    # Setup Twitter API (skip if in debug mode)
    twitter_client = None
    twitter_api_v1 = None
    if not debug_mode:
        twitter_client, twitter_api_v1 = setup_twitter_api()
        if not twitter_client or not twitter_api_v1:
            print("Failed to setup Twitter API. Exiting.")
            return

    # 1. Load latest event info
    latest_event = r2.read_json_file("metadata/latest_event_border_info.json")

    if latest_event["EventType"] not in [3, 4]:
        print("EventType not eligible. Exiting.")
        return

    now = time_utils.now_jst()
    start_at = time_utils.parse_jst_time(latest_event["StartAt"])
    end_at = time_utils.parse_jst_time(latest_event["EndAt"])

    if not (start_at <= now <= end_at):
        print("Current time is outside event period. Exiting.")
        return

    # 2. Collect prediction data for all borders
    border_predictions = {}
    prediction_timestamp = None
    
    for border, path in BORDER_FILES.items():
        pred = r2.read_json_file(path)

        # Check EventId
        if pred["metadata"]["raw"]["id"] != latest_event["EventId"]:
            raise Exception(f"Prediction for event {latest_event['EventId']} not available for border {border}")

        # Extract info
        event_name = latest_event["EventName"]
        event_end_time = latest_event["EndAt"]
        event_len_days = (len(pred["data"]["raw"]["target"]) - 1) * 0.5 / 24  # 30min steps

        # Calculate progress percentage
        last_known_step = pred["metadata"]["raw"]["last_known_step_index"]
        total_steps = len(pred["data"]["raw"]["target"])
        progress_percentage = (last_known_step + 1) / total_steps * 100

        # Get prediction file timestamp from R2 (use the first one we encounter)
        if prediction_timestamp is None:
            prediction_timestamp = r2.get_file_timestamp(path)
            print(f"DEBUG: Raw prediction timestamp for border {border}: {prediction_timestamp}")
            print(f"DEBUG: Timestamp type: {type(prediction_timestamp)}")

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

        neighbors_info = []
        for rank, neighbor_data in pred["metadata"]["normalized"]["neighbors"].items():
            rank_int = int(rank)
            raw_length = neighbor_data["raw_length"]
            is_normalized = raw_length != len(pred["data"]["raw"]["target"])
            # Calculate neighbor event length in days
            neighbor_event_length = (raw_length - 1) * 0.5 / 24  # 30min steps
            neighbors_info.append((rank_int, neighbor_data["name"], pred["data"]["normalized"]["neighbors"][rank][ -1], is_normalized, neighbor_event_length))

        # Sort neighbors by rank
        neighbors_info.sort(key=lambda x: x[0])

        # Generate image
        if debug_mode:
            image_path = f"debug/summary_border_{border}.png"
        else:
            image_path = f"output/summary_border_{border}.png"
            
        image_generator.generate_summary_image(
            event_name, border, event_len_days, final_score, ci_90, ci_75, neighbors_info, 
            event_end_time, progress_percentage, prediction_timestamp, output_path=image_path
        )
        print(f"Generated image for border {border}: {image_path}")

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
    
    tweet_text = f"{event_name}\n"
    tweet_text += f"予測生成日時：{pred_time_str}\n"
    
    # Add predictions for each border
    for border in sorted(BORDER_FILES.keys()):
        if border in border_predictions:
            final_score = border_predictions[border]['final_score']
            tweet_text += f"{border}位予測値：{final_score:,}\n"
    
    # 4. Post tweet with all images
    image_paths = []
    for border in BORDER_FILES.keys():
        if debug_mode:
            image_path = f"debug/summary_border_{border}.png"
        else:
            image_path = f"output/summary_border_{border}.png"
        image_paths.append(image_path)
    
    # Post to Twitter with all images (Twitter supports up to 4 images)
    try:
        post_to_twitter(twitter_client, twitter_api_v1, image_paths, tweet_text, debug_mode)
        print("Tweet posted successfully with predictions for all borders!")
    except Exception as e:
        print(f"Failed to post tweet: {e}")
    
    # Clean up image files if not in debug mode
    if not debug_mode:
        for image_path in image_paths:
            try:
                os.remove(image_path)
                print(f"Cleaned up image file: {image_path}")
            except OSError:
                pass

if __name__ == "__main__":
    main()
