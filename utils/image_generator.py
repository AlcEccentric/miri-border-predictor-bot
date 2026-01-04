from PIL import Image, ImageDraw, ImageFont
import textwrap
import platform
import os
from datetime import datetime
import pytz

def get_bundled_font():
    """Get font from the local fonts directory"""
    # Get the directory where this script is located
    current_dir = os.path.dirname(os.path.abspath(__file__))
    fonts_dir = os.path.join(os.path.dirname(current_dir), "fonts")
    
    # Try bundled fonts first - prioritize MOBO font
    bundled_fonts = [
        "MOBO-Font11/MOBO-Regular.otf",  # Your provided MOBO font
        "MOBO-Font11/MOBO-Bold.otf",
        "MOBO-Font11/MOBO-SemiBold.otf",
    ]
    
    for font_name in bundled_fonts:
        font_path = os.path.join(fonts_dir, font_name)
        if os.path.exists(font_path):
            return font_path
    
    return None

# Try bundled fonts first, then system fonts
FONT_PATH = get_bundled_font()

def generate_summary_image(event_name: str, border: int, event_length_days: float,
                           final_score: int, ci_90: tuple, ci_75: tuple,
                           neighbors: list, event_end_time: str, progress_percentage: float, 
                           prediction_timestamp, output_path="summary.png", outlier_direction=None):

    # Calculate dynamic heights
    has_warning = outlier_direction in ('high', 'low')
    # Neighbors section: header + rows + bottom padding for footnote (extra margin)
    neighbors_table_height = 140 + len(neighbors) * 73 + 80
    width, height = 1200, 700 + neighbors_table_height
    img = Image.new("RGB", (width, height), color=(250, 250, 250))  # Light gray background
    draw = ImageDraw.Draw(img)
    
    # Load fonts - throw exception if font not found
    if not FONT_PATH or not os.path.exists(FONT_PATH):
        raise FileNotFoundError(f"Japanese font not found. Please add a Japanese font to the fonts/ directory. Expected MOBO font at: {FONT_PATH}")
    
    try:
        font_title = ImageFont.truetype(FONT_PATH, 40)
        font_subtitle = ImageFont.truetype(FONT_PATH, 32)
        font_section = ImageFont.truetype(FONT_PATH, 24)
        font_text = ImageFont.truetype(FONT_PATH, 24)  # Increased from 20 to 24
        font_small = ImageFont.truetype(FONT_PATH, 20)  # Increased from 16 to 20
        
        # Load bold font for scores
        bold_font_path = FONT_PATH.replace("MOBO-Regular.otf", "MOBO-Bold.otf")
        if os.path.exists(bold_font_path):
            font_bold = ImageFont.truetype(bold_font_path, 24)  # Increased from 20 to 24
            font_bold_large = ImageFont.truetype(bold_font_path, 28)  # Increased from 24 to 28
            font_bold_small = ImageFont.truetype(bold_font_path, 20)  # Increased from 16 to 20
        else:
            # Fallback to regular font if bold not available
            font_bold = font_text
            font_bold_large = font_text
            font_bold_small = font_small
    except (OSError, IOError) as e:
        raise RuntimeError(f"Failed to load font from {FONT_PATH}: {e}")
    
    # Color scheme
    primary_color = (41, 128, 185)    # Blue
    secondary_color = (52, 73, 94)    # Dark gray
    accent_color = (231, 76, 60)      # Red
    text_color = (44, 62, 80)         # Dark blue-gray
    bg_section = (255, 255, 255)      # White
    border_color = (189, 195, 199)    # Light gray
        

    # Helper function to draw rounded rectangle
    def draw_rounded_rect(x, y, w, h, radius, fill_color, outline_color=None):
        draw.rectangle([x + radius, y, x + w - radius, y + h], fill=fill_color, outline=outline_color)
        draw.rectangle([x, y + radius, x + w, y + h - radius], fill=fill_color, outline=outline_color)
        draw.pieslice([x, y, x + 2*radius, y + 2*radius], 180, 270, fill=fill_color, outline=outline_color)
        draw.pieslice([x + w - 2*radius, y, x + w, y + 2*radius], 270, 360, fill=fill_color, outline=outline_color)
        draw.pieslice([x, y + h - 2*radius, x + 2*radius, y + h], 90, 180, fill=fill_color, outline=outline_color)
        draw.pieslice([x + w - 2*radius, y + h - 2*radius, x + w, y + h], 0, 90, fill=fill_color, outline=outline_color)

    # Format timestamps for display
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
    
    try:
        if event_end_time.endswith('+09:00'):
            end_time_str = event_end_time.replace('+09:00', '').replace('T', ' ') + " JST"
        else:
            end_time_str = event_end_time
    except:
        end_time_str = event_end_time

    # 1. TITLE SECTION
    draw.text((30, 25), event_name, fill=primary_color, font=font_title)
    
    # 2. PREDICTION SECTION (Border, Final Prediction, CIs)
    pred_section_y = 80
    # Keep original height when no warning; add extra bottom padding only when warning exists
    pred_section_height = 230 + (40 if has_warning else 0)
    draw_rounded_rect(20, pred_section_y, width-40, pred_section_height, 10, bg_section, border_color)
    
    # Border as prominent subtitle
    draw.text((35, pred_section_y + 25), f"{border}位予測", fill=text_color, font=font_subtitle)
    
    # Prediction data in single column
    col1_x = 35
    y_offset = pred_section_y + 70
    
    # Main prediction with consistent font size
    draw.text((col1_x, y_offset), f"予測値: ", fill=text_color, font=font_text)
    score_x = col1_x + draw.textlength("予測値: ", font=font_text)
    
    # Draw the score in same size bold font with accent color
    score_text = f"{final_score:,}"
    draw.text((score_x, y_offset), score_text, fill=primary_color, font=font_bold)
    # 90% CI with bold numbers and subtle emphasis (increased spacing)
    draw.text((col1_x, y_offset + 40), f"90% 信頼区間: ", fill=text_color, font=font_text)
    ci90_x = col1_x + draw.textlength("90% 信頼区間: ", font=font_text)
    draw.text((ci90_x, y_offset + 40), f"{ci_90[0]:,} ～ {ci_90[1]:,}", fill=secondary_color, font=font_bold)
    
    # 75% CI with bold numbers and subtle emphasis (increased spacing)
    draw.text((col1_x, y_offset + 75), f"75% 信頼区間: ", fill=text_color, font=font_text)
    ci75_x = col1_x + draw.textlength("75% 信頼区間: ", font=font_text)
    draw.text((ci75_x, y_offset + 75), f"{ci_75[0]:,} ～ {ci_75[1]:,}", fill=secondary_color, font=font_bold)
    draw.text((col1_x, y_offset + 110), f"予測生成日時: {pred_time_str}", fill=text_color, font=font_text)

    # Outlier warning within the prediction section (under generation time)
    if has_warning:
        try:
            # Anchor near bottom of prediction box with safe margin
            warn_y = pred_section_y + pred_section_height - 50
            warn_x = col1_x
            direction_short = '高め' if outlier_direction == 'high' else '低め'
            result_trend_text = '下振れ' if outlier_direction == 'high' else '上振れ'
            warn_text = f"※このボーダーは過去同タイプ比で{direction_short}のため、予測は{result_trend_text}しやすいです。"
            # Draw full text in the same size as other text in the section,
            # then overlay only result_trend_text in red/bold
            draw.text((warn_x, warn_y), warn_text, fill=text_color, font=font_text)
            try:
                idx = warn_text.find(result_trend_text)
                if idx != -1:
                    before = warn_text[:idx]
                    before_w = draw.textlength(before, font=font_text)
                    draw.text((warn_x + before_w, warn_y), result_trend_text, fill=accent_color, font=font_bold)
            except Exception:
                draw.text((warn_x, warn_y), warn_text, fill=accent_color, font=font_text)
        except Exception:
            pass
    
    # 3. METADATA SECTION
    meta_section_y = 330
    draw_rounded_rect(20, meta_section_y, width-40, 190, 10, bg_section, border_color)
    draw.text((35, meta_section_y + 20), "イベント情報", fill=secondary_color, font=font_subtitle)
    
    # Metadata in single column with increased spacing
    y_offset = meta_section_y + 60
    draw.text((col1_x, y_offset), f"終了日時: {end_time_str}", fill=text_color, font=font_text)
    draw.text((col1_x, y_offset + 35), f"期間: {event_length_days:.2f} 日", fill=text_color, font=font_text)
    draw.text((col1_x, y_offset + 70), f"進行度: {progress_percentage:.1f}%", fill=text_color, font=font_text)
    
    # 4. NEIGHBORS TABLE SECTION
    table_y = 540
    draw_rounded_rect(20, table_y, width-40, neighbors_table_height, 10, bg_section, border_color)
    draw.text((35, table_y + 20), "類似イベント", fill=secondary_color, font=font_subtitle)
    
    # Table headers - simplified
    header_y = table_y + 65
    draw.rectangle([35, header_y, width-35, header_y + 35], fill=(240, 240, 240), outline=border_color)
    draw.text((45, header_y + 4), "順位", fill=secondary_color, font=font_text)
    draw.text((100, header_y + 4), "イベント名", fill=secondary_color, font=font_text)
    
    # Table rows - 2-row design for each neighbor
    row_y = header_y + 40
    for rank, name, score, normalized, neighbor_length in neighbors:
        norm_text = "正規化済み*" if normalized else "未正規化*"
        
        # Fixed row height for 2-row design (increased for better spacing)
        row_height = 65
        
        # Alternate row colors for all rows (consistent background)
        if rank % 2 == 0:
            draw.rectangle([35, row_y, width-35, row_y + row_height], fill=(248, 248, 248))
        else:
            draw.rectangle([35, row_y, width-35, row_y + row_height], fill=(255, 255, 255))
        
        # First row: Rank and Event Name
        draw.text((45, row_y + 10), str(rank), fill=text_color, font=font_text)
        
        # Truncate name if still too long for one line
        max_name_chars = 80  # Maximum characters for event name
        display_name = name[:max_name_chars] + "..." if len(name) > max_name_chars else name
        draw.text((100, row_y + 10), display_name, fill=text_color, font=font_text)
        
        # Second row: Score, Duration, and Normalization Status (with better spacing)
        # Draw score label
        draw.text((100, row_y + 40), "最終スコア: ", fill=text_color, font=font_small)
        score_label_width = draw.textlength("最終スコア: ", font=font_small)
        
        # Draw score in bold
        draw.text((100 + score_label_width, row_y + 40), f"{score:,}", fill=text_color, font=font_bold_small)
        score_width = draw.textlength(f"{score:,}", font=font_bold_small)
        
        # Draw remaining info
        remaining_text = f"    期間: {neighbor_length:.2f}日    {norm_text}"
        draw.text((100 + score_label_width + score_width, row_y + 40), remaining_text, fill=text_color, font=font_small)
        
        row_y += row_height + 8  # Increased spacing between entries

    # Add footnote within the table section, anchored near the bottom with extra margin
    footnote_y = table_y + neighbors_table_height - 40  # 45px from bottom
    footnote_text = "*イベント期間が現在のイベントと異なる場合、正規化が適用されます。詳細は yuenimillion.live をご覧ください。"
    draw.text((45, footnote_y), footnote_text, fill=text_color, font=font_small)

    img.save(output_path)
    return output_path
