import discord
from discord.ext import tasks
import google.generativeai as genai
import os
import random
import asyncio
from datetime import datetime, timedelta, time
import pytz # タイムゾーン扱うために追加 (pip install pytz が必要かも)

# --- 秘密の鍵を読み込む ---
from dotenv import load_dotenv
load_dotenv() # .env ファイルから秘密の鍵を読み込む

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# --- Botの設定 ---
# 必要な権限（インテント）を設定
intents = discord.Intents.default()
intents.messages = True         # メッセージの受信
intents.message_content = True  # メッセージの内容を読む
bot = discord.Client(intents=intents) # Clientでシンプルに作る

# --- Gemini（脳みソ）の設定 ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash') # 最新の高速モデル
    print("Gemini（脳みソ）の準備OK！")
except Exception as e:
    print(f"！！！エラー：Geminiに接続できませんでした。APIキーは合ってる？: {e}")
    exit() # GeminiがダメならBot動いても意味ないので終了

# --- Botが使う変数（状態を記憶する） ---
last_checked_time = None # 最後にチェックした時間
is_first_check_of_day = True # その日の初回チェックか
did_daily_tweet = False # 日常ツイートしたか

# 日本のタイムゾーン
JST = pytz.timezone('Asia/Tokyo')

# ----------------------------------------
# ★★★ 神ロジックの「核」！★★★
# (「浮上タイミング」をチェックし続けるループ処理)
# ----------------------------------------
@tasks.loop(seconds=60) # 60秒に1回、この関数が動く
async def check_activity_loop():
    global last_checked_time, is_first_check_of_day, did_daily_tweet
    
    try:
        # --- 今が「浮上タイミング」か計算する ---
        now = datetime.now(JST)
        is_holiday = now.weekday() >= 5 # 土日か？ (5=土, 6=日)
        
        # 浮上する時間リスト
        # (平日: 21, 22, 23時 / 休日: 18, 19, 20, 21, 22, 23時)
        target_hours = []
        if is_holiday:
            target_hours = [18, 19, 20, 21, 22, 23]
        else:
            target_hours = [21, 22, 23]
            
        # 今が「浮上すべき時間帯」か？
        if now.hour not in target_hours:
            # print(f"({now.strftime('%H:%M:%S')}) 浮上時間外です。") # デバッグ用
            return # 浮上時間じゃないなら何もしない
            
        # --- 浮上タイミング！（±5分ランダムをここでチェック） ---
        
        # （簡易的な実装：その時間の「最初の10分間」の「どこか」で1回だけ動くようにする）
        # ※本当はもっと厳密に「±5分」を計算すべきだけど、まずはシンプルに！
        
        # 毎時0分～9分の間に、1回だけ動かす
        if now.minute >= 10:
             # print(f"({now.strftime('%H:%M:%S')}) {now.hour}時のチェック時間は過ぎました。") # デバッグ用
            return
            
        # この時間帯に、もうチェックしてないか？
        if last_checked_time and last_checked_time.hour == now.hour:
            # print(f"({now.strftime('%H:%M:%S')}) {now.hour}時はもうチェック済みです。") # デバッグ用
            return

        # --- よっしゃ！浮上するぜ！ ---
        # （ランダムな秒数、待機して「人間っぽさ」を出す）
        await asyncio.sleep(random.randint(1, 10)) # 1～10秒待つ
        
        print(f"--- ( {now.strftime('%Y-%m-%d %H:%M:%S')} ) ---")
        print(f"★★★ 浮上タイミング！ チェック開始！ ★★★")
        
        # ステータスを「勉強中」とか「受験期」っぽくする（カスタムステータス）
        # ※Botのカスタムステータス設定はちょっと複雑なので、まずは「オンライン」にするだけ
        await bot.change_presence(status=discord.Status.online)
        
        # タイピング中にして「人間っぽさ」を出す
        # (発言するチャンネルIDが必要。ここでは仮に 'YOUR_CHANNEL_ID' としてる)
        # channel = bot.get_channel(YOUR_CHANNEL_ID) # ← ★★★ ここは後で設定 ★★★
        # if channel:
        #     async with channel.typing():
        #         await asyncio.sleep(random.randint(2, 5)) # 2～5秒タイピング中…

        # ----------------------------------
        # ★★★ ここにロジックを足していく ★★★
        # ----------------------------------
        
        # (ロジックC) 定時連絡（ロールプレイ）
        # その日初の浮上？
        if is_first_check_of_day:
            print("[ロジックC] 今日初の浮上！受験生ツイートします。")
            # prompt = "僕は受験期の男子高校生。塾や勉強で疲れたー、みたいな日常的なツイートを1個、タメ口で短く作って。"
            # response = model.generate_content(prompt)
            # await channel.send(response.text) # ← ★★★ チャンネル設定したら動かす ★★★
            is_first_check_of_day = False
            did_daily_tweet = True # 定時連絡したら日常ツイートはしない

        # (ロジックC) 寝るツイート
        if now.hour == 23:
            print("[ロジックC] 23時だ！寝るツイートします。")
            # prompt = "僕は受験期の男子高校生。「そろそろ寝るわー」みたいな感じの、おやすみツイートを1個、タメ口で短く作って。"
            # response = model.generate_content(prompt)
            # await channel.send(response.text) # ← ★★★ チャンネル設定したら動かす ★★★
            
        # (ロジックD) 日常ツイート（1日1回）
        if not did_daily_tweet:
            print("[ロジックD] 日常ツイートします。")
            # prompt = "僕は受験期の男子高校生。「ラーメン食いたい」とか「今日寒い」みたいな、勉強とは関係ない日常ツイートを1個、タメ口で短く作って。"
            # response = model.generate_content(prompt)
            # await channel.send(response.text) # ← ★★★ チャンネル設定したら動かす ★★★
            did_daily_tweet = True


        # (ロジックA) メンション確認
        print("[ロジックA] メンション確認します（まだ機能してません）")
        # ★★★ ここに「前回の浮上時間から今までのメンション」を探すコードを書く ★★★
        
        # (ロジックB) エゴサ確認
        print("[ロジックB] エゴサ確認します（まだ機能してません）")
        # ★★★ ここに「直近10件に自分の発言があるか」探すコードを書く ★★★


        # ----------------------------------
        # チェック完了！
        # ----------------------------------
        print("★★★ チェック完了！ 次の浮上まで待機します。★★★")
        
        # 「オフライン」に戻して人間っぽさを出す
        await bot.change_presence(status=discord.Status.invisible)
        
        # 最後にチェックした時間を記録
        last_checked_time = now
        
    except Exception as e:
        print(f"！！！エラー：ループ処理中に何か起きました: {e}")

# ----------------------------------------
# Botが起動したときに呼ばれる処理
# ----------------------------------------
@bot.event
async def on_ready():
    print(f'--- {bot.user} (ハル) がDiscordにログインしました ---')
    print('受験期モード、起動します...')
    
    # 毎日0時（JST）にフラグをリセットするタスクも入れたいけど、まずはシンプルに
    # （Botが動いてる日付が変わったらリセットする）
    
    # 浮上タイミングのチェックループを開始！
    check_activity_loop.start()
    
    # 最初は「オフライン（透明）」になって潜伏する
    await bot.change_presence(status=discord.Status.invisible)

# ----------------------------------------
# Botを起動！
# ----------------------------------------
if DISCORD_TOKEN:
    try:
        print("「ハル」を起動します...")
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        print(f"！！！エラー：Botの起動に失敗しました。Discordトークンは合ってる？: {e}")
else:
    print("！！！エラー：DISCORD_TOKEN が .env ファイルに設定されていません。")