from flask import Flask, render_template, request, session, jsonify, send_from_directory
import os
import requests
import base64
import secrets
import logging

# 假设这些常量已经定义
OPENAI_API_KEY = "sk-VfFQdzQTPS9ZVzmKtvsjOwn6Hf7Cyt4k5vT509skHbIxTfCG"
BAIDU_ASR_URL = "https://vop.baidu.com/server_api"
BAIDU_TTS_URL = "http://tsn.baidu.com/text2audio"
# 补充百度 API Key 和 Secret Key，需替换为实际值
BAIDU_API_KEY = "4SsOre5CgY3vPMW0SiEEMzAC"
BAIDU_SECRET_KEY = "uAEqM09Xh3KB5UGRD5UEA9TfKUrKc8N3"

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # 用于会话管理
app.config['UPLOAD_FOLDER'] = 'uploads'
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# 配置日志
logging.basicConfig(level=logging.DEBUG)

# 允许的文件类型
ALLOWED_EXTENSIONS = {'wav', 'mp3'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_baidu_token():
    # 实现获取百度token的逻辑
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {
        "grant_type": "client_credentials",
        "client_id": BAIDU_API_KEY,
        "client_secret": BAIDU_SECRET_KEY
    }
    response = requests.post(url, params=params)
    if response.status_code == 200:
        result = response.json()
        return result.get("access_token")
    else:
        return None


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
    token = get_baidu_token()
    if not token:
        return None
    params = {
        'cuid': '123456PYTHON',
        'token': token,
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


def text_to_speech(text, lang='zh', per=4):
    url = BAIDU_TTS_URL  # 确保这里使用的是正确的变量名
    lang_per = {
        'zh': 6221,  # 假设10为臻品音库中中文合适发音人的标识
        'en': 4105,  # 假设11为臻品音库中英文合适发音人的标识
        # 'ja': 具体日语音色代码,
        # 'fr': 具体法语音色代码,
        # 'ko': 具体韩语音色代码
    }
    per = lang_per.get(lang, per)
    token = get_baidu_token()
    if not token:
        return None
    params = {
        'tex': text,
        'lan': lang,
        'tok': token,
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
        "temperature": 0.8,
        "max_tokens": 1000
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        result = response.json()
        return result['choices'][0]['message']['content'].strip()  # 返回 GPT-4 的响应
    else:
        return f"Error: {response.status_code}, {response.text}"


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

            # 保存语音文件
            audio_data = text_to_speech(gpt_reply, lang=language, per=int(voice))
            if audio_data:
                # 创建对话文件夹
                conversation_folder = os.path.join(app.config['UPLOAD_FOLDER'], str(len(history) // 2))
                if not os.path.exists(conversation_folder):
                    os.makedirs(conversation_folder)
                audio_file_path = os.path.join(conversation_folder, 'reply.mp3')
                with open(audio_file_path, 'wb') as f:
                    f.write(base64.b64decode(audio_data))

            return render_template('index.html', text_reply=gpt_reply, audio_reply=audio_data, history=history)
        elif file and allowed_file(file.filename):
            # 处理语音输入
            filename = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filename)
            # 语音识别
            speech_text = recognize_speech(filename, lang=language)
            if not speech_text:
                return jsonify({'error': '语音识别失败'}), 400
            # 使用 GPT 回复
            gpt_reply = generate_gpt_reply(speech_text, history)
            # 更新对话历史
            history.append({"role": "user", "content": speech_text})
            history.append({"role": "assistant", "content": gpt_reply})
            session['history'] = history

            # 保存语音文件
            audio_data = text_to_speech(gpt_reply, lang=language, per=int(voice))
            if audio_data:
                # 创建对话文件夹
                conversation_folder = os.path.join(app.config['UPLOAD_FOLDER'], str(len(history) // 2))
                if not os.path.exists(conversation_folder):
                    os.makedirs(conversation_folder)
                audio_file_path = os.path.join(conversation_folder, 'reply.mp3')
                with open(audio_file_path, 'wb') as f:
                    f.write(base64.b64decode(audio_data))

            return render_template('index.html', text_reply=gpt_reply, audio_reply=audio_data, history=history)
        return jsonify({'error': '没有提供有效的输入'}), 400
    return render_template('index.html', history=session.get('history', []))


@app.route('/uploads/<int:conversation_id>/reply.mp3')
def serve_audio(conversation_id):
    conversation_folder = os.path.join(app.config['UPLOAD_FOLDER'], str(conversation_id))
    return send_from_directory(conversation_folder, 'reply.mp3')


@app.route('/delete_conversation/<int:conversation_id>', methods=['POST'])
def delete_conversation(conversation_id):
    # 删除对话文件夹
    conversation_folder = os.path.join(app.config['UPLOAD_FOLDER'], str(conversation_id))
    if os.path.exists(conversation_folder):
        try:
            import shutil
            shutil.rmtree(conversation_folder)
            app.logger.info(f"成功删除对话文件夹: {conversation_folder}")
        except Exception as e:
            app.logger.error(f"删除文件夹时出错: {e}")
            return jsonify({'message': '删除对话文件夹失败'}), 500

    # 更新会话历史
    history = session.get('history', [])
    start_index = (conversation_id - 1) * 2
    end_index = start_index + 2

    # 检查索引是否合法
    if 0 <= start_index < len(history) and 0 <= end_index <= len(history):
        del history[start_index:end_index]
        session['history'] = history
        app.logger.info(f"成功更新会话历史，新的历史长度: {len(history)}")
    else:
        app.logger.error(f"更新会话历史时索引错误，start_index: {start_index}, end_index: {end_index}, history长度: {len(history)}")
        return jsonify({'message': '更新会话历史时索引错误'}), 500

    return jsonify({'message': '对话已删除'}), 200


if __name__ == '__main__':
    app.run(debug=True)