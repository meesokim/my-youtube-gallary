import os
import json
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from jinja2 import Environment, FileSystemLoader
import urllib.parse

# 설정값
PAGES_URL = "https://meesokim.github.io/my-youtube-gallary"
OUTPUT_DIR = "docs"

def create_pptx(video_data, output_path):
    """ 한 페이지안에 영상을 깔끔하게 요약한 PPTX 생성 """
    prs = Presentation()
    # 16:9 와이드스크린 설정
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    
    blank_slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank_slide_layout)

    # 배경색 설정 (진한 네이비)
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor(0x1a, 0x1a, 0x2e)
    
    # 카테고리 라벨
    cat_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(3), Inches(0.4))
    tf_cat = cat_box.text_frame
    p_cat = tf_cat.paragraphs[0]
    p_cat.text = f"[ {video_data['category']} ]"
    p_cat.font.name = "Malgun Gothic"
    p_cat.font.size = Pt(14)
    p_cat.font.bold = True
    p_cat.font.color.rgb = RGBColor(0xff, 0x6b, 0x6b)
    
    # 제목 상자 추가
    title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.7), Inches(12.333), Inches(1.0))
    tf_title = title_box.text_frame
    tf_title.word_wrap = True
    p_title = tf_title.paragraphs[0]
    p_title.text = video_data['title']
    p_title.font.name = "Malgun Gothic"
    p_title.font.size = Pt(32)
    p_title.font.bold = True
    p_title.font.color.rgb = RGBColor(0xff, 0xff, 0xff)
    
    # 구분선 역할의 얇은 사각형
    line_shape = slide.shapes.add_shape(
        1, Inches(0.5), Inches(1.75), Inches(2), Inches(0.04)
    )
    line_shape.fill.solid()
    line_shape.fill.fore_color.rgb = RGBColor(0x64, 0xb5, 0xf6)
    line_shape.line.fill.background()
    
    # Overview
    ov_box = slide.shapes.add_textbox(Inches(0.5), Inches(2.0), Inches(12.333), Inches(1.2))
    tf_ov = ov_box.text_frame
    tf_ov.word_wrap = True
    p_ov = tf_ov.paragraphs[0]
    p_ov.text = video_data['overview']
    p_ov.font.name = "Malgun Gothic"
    p_ov.font.size = Pt(16)
    p_ov.font.color.rgb = RGBColor(0xcc, 0xcc, 0xcc)
    
    # Key Points
    content_box = slide.shapes.add_textbox(Inches(0.5), Inches(3.4), Inches(12.333), Inches(3.2))
    tf_content = content_box.text_frame
    tf_content.word_wrap = True
    
    for i, point in enumerate(video_data['points']):
        if i == 0:
            p = tf_content.paragraphs[0]
        else:
            p = tf_content.add_paragraph()
        p.text = f"▸ {point}"
        p.font.name = "Malgun Gothic"
        p.font.size = Pt(13)
        p.font.color.rgb = RGBColor(0xee, 0xee, 0xee)
        p.space_after = Pt(8)
        
    # 하단 링크 및 키워드 바
    meta_box = slide.shapes.add_textbox(Inches(0.5), Inches(6.8), Inches(12.333), Inches(0.5))
    tf_meta = meta_box.text_frame
    p_meta = tf_meta.paragraphs[0]
    p_meta.text = f"Keywords: {video_data['keywords']}  |  🔗 https://youtu.be/{video_data['youtube_id']}"
    p_meta.font.name = "Malgun Gothic"
    p_meta.font.size = Pt(10)
    p_meta.font.color.rgb = RGBColor(0x88, 0x88, 0x88)
    
    prs.save(output_path)

def build_site():
    # 출력 디렉토리 생성
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 기존 빌드 결과물 정리 (기존에 있던 .html, .pptx 파일만 지워줌)
    for filename in os.listdir(OUTPUT_DIR):
        if filename.endswith(".html") or filename.endswith(".pptx"):
            file_path = os.path.join(OUTPUT_DIR, filename)
            try:
                os.remove(file_path)
                print(f"[-] 기존 파일 제거: {file_path}")
            except Exception as e:
                print(f"[!] 기존 파일 제거 중 오류 발생: {e}")
                
    # 데이터 로드
    with open('data/videos.json', 'r', encoding='utf-8') as f:
        videos = json.load(f)
        
    env = Environment(loader=FileSystemLoader('templates'))
    
    # URL 인코딩을 위한 헬퍼 함수 등록
    env.globals['encode_url'] = urllib.parse.quote
    env.globals['pages_url'] = PAGES_URL
    
    # 1. 상세 페이지 및 PPTX 생성
    preview_template = env.get_template('video.html')
    for video in videos:
        filename = video['filename']
        
        # PPTX 저장
        pptx_path = os.path.join(OUTPUT_DIR, f"{filename}.pptx")
        create_pptx(video, pptx_path)
        print(f"[+] PPTX 생성: {pptx_path}")
        
        # 상세 HTML 저장
        rendered_html = preview_template.render(video=video)
        html_path = os.path.join(OUTPUT_DIR, f"{filename}.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(rendered_html)
        print(f"[+] HTML 생성: {html_path}")
            
    # 2. 메인 index.html 생성
    index_template = env.get_template('index.html')
    rendered_index = index_template.render(videos=videos)
    index_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(rendered_index)
    print(f"[+] Index 생성: {index_path}")
    print(f"[*] 총 {len(videos)}개 영상 처리 완료!")

if __name__ == "__main__":
    build_site()
