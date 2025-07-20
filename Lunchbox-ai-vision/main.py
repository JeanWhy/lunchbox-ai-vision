import base64
import re
import asyncio
import os
import tempfile
from flask import Flask, render_template, request, redirect, url_for, jsonify, session
import openai
import uuid

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
openai.api_key = "openai.api_key"

# 임시 파일 저장소 (메모리에 저장)
temp_storage = {}

# 다국어 지원을 위한 텍스트 사전
TEXTS = {
    'ko': {
        'upload_title': 'Upload a photo, get a lunchbox idea!',
        'choose_file': '📁 Upload Photo',
        'change_file': '📁 Change Photo',
        'no_file_selected': '선택된 파일이 없습니다',
        'selected_file': '선택된 파일:',
        'get_recommendation': 'Get recommendation',
        'analyzing': '분석 중... (3초 후 결과 페이지로 이동)',
        'ai_result_title': '🍱 AI 도시락 추천 결과',
        'custom_menu': '🎉 우리 아이를 위한 맞춤 도시락 메뉴',
        'custom_description': '영양 가득, 맛도 가득한 도시락을 만들어보세요!',
        'ai_generating': 'AI가 맞춤 도시락 메뉴를 추천하고 있어요...',
        'please_wait': '잠시만 기다려주세요!',
        'new_recommendation': '🔄 새로운 메뉴 추천받기',
        'ingredients': '🥬 재료',
        'instructions': '👨‍🍳 만드는 법',
        'nutrition': '💪 영양정보',
        'image_generating': '이미지 생성 중...',
        'error_occurred': '❌ 오류가 발생했습니다',
        'try_again': '다시 시도해주세요.',
        'retry_button': '다시 시도하기',
        'prompt_text': '이 사진에 보이는 재료로 만들 수 있는 초등학생 도시락 메뉴 3-4개를 추천해줘. 각 메뉴마다 다음 형식으로 작성해줘:\n\n**메뉴명**\n재료: (사용할 재료들)\n만드는 법: (간단한 조리법)\n영양정보: (어떤 영양소가 좋은지)\n\n한국 스타일 도시락으로, 아이들이 좋아할 만한 메뉴로 추천해줘!',
        'image_prompt': '한국 스타일 도시락 메뉴 \'{menu_name}\' 완성된 요리 사진, 아이들이 좋아할 만한 귀여운 스타일, 밝고 맛있어 보이는, 고화질'
    },
    'en': {
        'upload_title': 'Upload a photo, get a lunchbox idea!',
        'choose_file': '📁 Upload Photo',
        'change_file': '📁 Change Photo',
        'no_file_selected': 'No file selected',
        'selected_file': 'Selected file:',
        'get_recommendation': 'Get recommendation',
        'analyzing': 'Analyzing... (Redirecting to results in 3 seconds)',
        'ai_result_title': '🍱 AI Lunchbox Recommendation Results',
        'custom_menu': '🎉 Custom Lunchbox Menu for Your Child',
        'custom_description': 'Create nutritious and delicious lunchboxes!',
        'ai_generating': 'AI is generating custom lunchbox menu recommendations...',
        'please_wait': 'Please wait a moment!',
        'new_recommendation': '🔄 Get New Menu Recommendation',
        'ingredients': '🥬 Ingredients',
        'instructions': '👨‍🍳 Instructions',
        'nutrition': '💪 Nutrition Info',
        'image_generating': 'Generating image...',
        'error_occurred': '❌ An error occurred',
        'try_again': 'Please try again.',
        'retry_button': 'Try Again',
        'prompt_text': 'Please recommend 3-4 elementary school lunchbox menus that can be made with the ingredients shown in this photo. Write each menu in the following format:\n\n**Menu Name**\nIngredients: (ingredients to use)\nInstructions: (simple cooking method)\nNutrition Info: (what nutrients are good)\n\nRecommend Korean-style lunchbox menus that children will enjoy!',
        'image_prompt': 'Korean style lunchbox menu \'{menu_name}\' finished dish photo, cute style that children will love, bright and delicious looking, high quality'
    }
}

def detect_language():
    """브라우저 언어 설정을 감지하여 한국어 또는 영어 결정"""
    accept_language = request.headers.get('Accept-Language', '')
    if 'ko' in accept_language.lower():
        return 'ko'
    return 'en'

def get_text(key, lang=None):
    """언어에 따른 텍스트 반환"""
    if lang is None:
        lang = detect_language()
    return TEXTS.get(lang, TEXTS['en']).get(key, key)

async def generate_menu_image(menu_name, lang='ko'):
    """각 메뉴에 대한 이미지 생성"""
    try:
        image_prompt = get_text('image_prompt', lang).format(menu_name=menu_name)
        response = openai.images.generate(
            model="dall-e-3",
            prompt=image_prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        return {menu_name: response.data[0].url}
    except Exception as e:
        print(f"이미지 생성 실패 for {menu_name}: {e}")
        return {menu_name: None}

async def generate_menu_images(menu_text, lang='ko'):
    """AI 응답에서 메뉴명을 추출하고 각 메뉴의 이미지를 비동기적으로 생성"""
    menu_names = re.findall(r'\*\*(.*?)\*\*', menu_text)
    tasks = [generate_menu_image(menu_name, lang) for menu_name in menu_names]

    menu_images = await asyncio.gather(*tasks)

    # 결과를 통합
    combined_images = {}
    for image in menu_images:
        combined_images.update(image)

    return combined_images

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        image_file = request.files["image"]
        image_bytes = image_file.read()
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        # 고유 ID 생성하여 임시 저장소에 저장
        request_id = str(uuid.uuid4())
        temp_storage[request_id] = {
            'image_base64': image_base64,
            'processing': True,
            'language': detect_language()
        }

        # request_id를 URL 파라미터로 전달
        return redirect(url_for('result', id=request_id))

    # GET 요청인 경우 index.html 반환
    lang = detect_language()
    return render_template("index.html", texts=TEXTS[lang], lang=lang)

@app.route("/result")
def result():
    request_id = request.args.get('id')
    if not request_id or request_id not in temp_storage:
        return redirect(url_for('index'))

    lang = temp_storage[request_id].get('language', detect_language())
    return render_template("result.html", request_id=request_id, texts=TEXTS[lang], lang=lang)

@app.route("/get_recommendation", methods=["POST"])
def get_recommendation():
    """AI 추천을 가져오는 API"""
    data = request.get_json()
    request_id = data.get('request_id')

    if not request_id or request_id not in temp_storage:
        return jsonify({"error": "No image data found"}), 400

    image_base64 = temp_storage[request_id]['image_base64']

    try:
        lang = temp_storage[request_id].get('language', 'ko')
        prompt_text = get_text('prompt_text', lang)

        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [{
                    "type": "text",
                    "text": prompt_text
                }, {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                    }
                }]
            }],
            temperature=0.7,
        )

        result = response.choices[0].message.content
        temp_storage[request_id]['processing'] = False

        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/generate_images", methods=["POST"])
def generate_images():
    """메뉴 이미지를 비동기적으로 생성하는 API"""
    data = request.get_json()
    menu_text = data.get('menu_text', '')
    request_id = data.get('request_id', '')

    # 언어 감지
    lang = 'ko'
    if request_id and request_id in temp_storage:
        lang = temp_storage[request_id].get('language', 'ko')

    # 비동기적으로 메뉴 이미지 생성
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    menu_images = loop.run_until_complete(generate_menu_images(menu_text, lang))

    return jsonify({"menu_images": menu_images})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)