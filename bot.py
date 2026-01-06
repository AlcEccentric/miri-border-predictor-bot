import sys
import os
import tweepy
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
from utils import r2, time_utils, image_generator

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
        print("Running in DEBUG MODE, meaning no tweets will be posted. \n Image & text will be saved to debug directory.")
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

    # Event name used in tweets/images
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

        # Extract info
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

        # Detect if this border is an outlier compared to historical neighbors
        # New rule: Only run if target and every neighbor each have > 50 points.
        # Compare the last 50 points index-by-index with strict inequalities.
        outlier_direction = None
        try:
            target = pred["data"]["normalized"].get("target")
            normalized_neighbors = pred["data"]["normalized"].get("neighbors")

            # Basic presence checks
            if not isinstance(target, list) or not normalized_neighbors or not isinstance(normalized_neighbors, dict):
                outlier_direction = None
            else:
                target_len = len(target)
                neighbor_items = list(normalized_neighbors.items())

                # Scope condition: current event and EVERY neighbor each have more than 50 points
                if target_len <= 50 or any(len(series) <= 50 for _, series in neighbor_items):
                    # Skip check entirely
                    outlier_direction = None
                else:
                    # Take the last 50 points for target and each neighbor
                    t_last = target[-50:]

                    all_above = True
                    all_below = True

                    # Index-by-index strict comparison across all neighbors
                    for i in range(50):
                        t_val = t_last[i]

                        # Validate numeric
                        if not isinstance(t_val, (int, float)) or (isinstance(t_val, float) and t_val != t_val):
                            all_above = False
                            all_below = False
                            break

                        # Retrieve neighbor values at aligned last-50 index
                        for _, series in neighbor_items:
                            n_val = series[-50 + i]
                            # Validate numeric and apply strict comparisons (no ties)
                            if not isinstance(n_val, (int, float)) or (isinstance(n_val, float) and n_val != n_val):
                                all_above = False
                                all_below = False
                                break
                            if not (t_val > n_val):
                                all_above = False
                            if not (t_val < n_val):
                                all_below = False
                        # Early exit if neither condition can hold
                        if not all_above and not all_below:
                            break

                    if all_above:
                        outlier_direction = 'high'
                    elif all_below:
                        outlier_direction = 'low'
                    else:
                        outlier_direction = None
        except Exception as e:
            if debug_mode:
                print(f"DEBUG: Exception in outlier detection: {e}")
            outlier_direction = None

        # Attach outlier info to stored predictions for later text output
        border_predictions[border]['outlier_direction'] = outlier_direction

        # Generate image
        if debug_mode:
            image_path = f"debug/summary_border_{border}.png"
        else:
            image_path = f"output/summary_border_{border}.png"

        image_generator.generate_summary_image(
            event_name, border, event_len_days, final_score, ci_90, ci_75, neighbors_info, 
            event_end_time, progress_percentage, prediction_timestamp, output_path=image_path,
            outlier_direction=outlier_direction
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
            # If outlier detected for this border, add a warning note
            outlier = border_predictions[border].get('outlier_direction')
            if outlier in ('high', 'low'):
                direction_text = '高め' if outlier == 'high' else '低め'
                result_trend_text = '下振れ' if outlier == 'high' else '上振れ'
                # Shortened warning to avoid exceeding tweet length
                tweet_text += f"  ※このボーダーは過去同タイプ比で{direction_text}のため、予測は{result_trend_text}注意。\n\n"
            else:
                tweet_text += "\n"
    
    # Add footnote
    tweet_text += "※CI: 信頼区間"
    
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
