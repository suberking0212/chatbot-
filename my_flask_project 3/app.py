import os
import base64
import secrets

import requests
from flask import Flask, request, jsonify, render_template, session
from werkzeug.utils import secure_filename

# 百度 API 的 Key 和 Secret
BAIDU_API_KEY = '4SsOre5CgY3vPMW0SiEEMzAC'
BAIDU_SECRET_KEY = 'uAEqM09Xh3KB5UGRD5UEA9TfKUrKc8N3'

# Little Wheat API Key (用于 GPT)
OPENAI_API_KEY = 'sk-VfFQdzQTPS9ZVzmKtvsjOwn6Hf7Cyt4k5vT509skHbIxTfCG'  # 请替换为你实际的 Little Wheat API 密钥

# 百度语音识别（ASR）接口 URL
BAIDU_ASR_URL = "https://vop.baidu.com/server_api"

# 百度语音合成（TTS）接口 URL
BAIDU_TTS_URL = "http://tsn.baidu.com/text2audio"

# 文件上传路径
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'wav', 'mp3', 'ogg'}

# 初始化 Flask 应用
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = secrets.token_hex(16)  # 用于会话管理

# 判断文件扩展名是否允许上传
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 语音识别（百度语音识别）
def recognize_speech(file_path, lang='zh'):
    lang_model_map = {
        'zh': 1536,  # 普通话
        'en': 1737,  # 英语
        'ja': 1936,  # 日语
        'fr': 1739,  # 法语
        'ko': 1946  # 韩语
    }
    dev_pid = lang_model_map.get(lang, 1536)

    with open(file_path, 'rb') as f:
        speech_data = f.read()

    url = BAIDU_ASR_URL
    params = {
        'cuid': '123456PYTHON',
        'token': get_baidu_token(),
        'dev_pid': dev_pid,
        'speech': base64.b64encode(speech_data).decode('utf-8'),
        'format': 'wav',
        'rate': 16000,
    }

    headers = {'Content-Type': 'application/json'}
    response = requests.post(url, json=params, headers=headers)
    result = response.json()

    if result.get('err_no') == 0:
        return result['result'][0]  # 返回语音识别的文本
    else:
        return None

# 获取百度 API token
def get_baidu_token():
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {
        'grant_type': 'client_credentials',
        'client_id': BAIDU_API_KEY,
        'client_secret': BAIDU_SECRET_KEY
    }
    response = requests.post(url, params=params)
    result = response.json()
    return result['access_token']

# 生成语音（百度语音合成）
def text_to_speech(text, lang='zh', per=4):
    url = BAIDU_TTS_URL
    lang_per = {
        'zh': 6221,  # 假设10为臻品音库中中文合适发音人的标识
        'en': 4105,  # 假设11为臻品音库中英文合适发音人的标识
        # 'ja': 具体日语音色代码,
        # 'fr': 具体法语音色代码,
        # 'ko': 具体韩语音色代码
    }
    per = lang_per.get(lang, per)
    params = {
        'tex': text,
        'lan': lang,
        'tok': get_baidu_token(),
        'ctp': 1,
        'cuid': '123456PYTHON',
        'vol': 8,  # 音量
        'spd': 6,  # 语速
        'pit': 5,  # 音调
        'aue': 3,  # MP3 格式
        'per': per  # 发音人
    }
    response = requests.post(url, data=params)
    if response.status_code == 200:
        return base64.b64encode(response.content).decode('utf-8')
    else:
        return None

# 处理文本输入（Little Wheat API）
def generate_gpt_reply(user_input, history=[]):
    url = "https://chatapi.littlewheat.com/v1/chat/completions"  # Little Wheat API 地址
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    messages = [{"role": "system", "content": "你是一个帮助解决问题的助手。"}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_input})

    data = {
        "model": "gpt-4o-mini",  # 使用的模型名称
        "messages": messages,
        "temperature": 0.75,
        "max_tokens": 500
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        result = response.json()
        return result['choices'][0]['message']['content'].strip()  # 返回 GPT-4 的响应
    else:
        return f"Error: {response.status_code}, {response.text}"

# Flask 路由：首页
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        text_input = request.form.get('text_input')
        language = request.form.get('language')  # 获取选择的语言
        voice = request.form.get('voice')  # 获取选择的音色
        file = request.files.get('file')
        # 获取对话历史
        history = session.get('history', [])
        if text_input:
            # 处理文本输入
            gpt_reply = generate_gpt_reply(text_input, history)
            # 更新对话历史
            history.append({"role": "user", "content": text_input})
            history.append({"role": "assistant", "content": gpt_reply})
            session['history'] = history
            audio_data = text_to_speech(gpt_reply, lang=language, per=int(voice))
            return render_template('index.html', text_reply=gpt_reply, audio_reply=audio_data)
        elif file and allowed_file(file.filename):
            # 处理语音输入
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            # 语音识别
            speech_text = recognize_speech(file_path, lang=language)
            if not speech_text:
                return jsonify({'error': '语音识别失败'}), 400
            # 使用 GPT 回复
            gpt_reply = generate_gpt_reply(speech_text, history)
            # 更新对话历史
            history.append({"role": "user", "content": speech_text})
            history.append({"role": "assistant", "content": gpt_reply})
            session['history'] = history
            audio_data = text_to_speech(gpt_reply, lang=language, per=int(voice))
            return render_template('index.html', text_reply=gpt_reply, audio_reply=audio_data)
        return jsonify({'error': '没有提供有效的输入'}), 400
    return render_template('index.html')



if __name__ == '__main__':
    app.run(debug=True)