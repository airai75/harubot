import discord
from discord.ext import tasks
import google.generativeai as genai
import os
import random
import asyncio
from datetime import datetime, timedelta, time
import pytz # タイムゾーン扱うために追加
from dotenv import load_dotenv

# --- 秘密の鍵を読み込む ---
load_dotenv() 

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
TARGET_CHANNEL_ID_STR = os.getenv('TARGET_CHANNEL_ID') # 発言するチャンネルID

# --- Botの設定 ---
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = discord.Client(intents=intents)

# --- Gemini（脳みソ）の設定 ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    print("Gemini（脳みソ）の準備OK！")
except Exception as e:
    print(f"！！！エラー：Geminiに接続できませんでした。APIキーは合ってる？: {e}")
    exit()

# --- Botが使う変数（状態を記憶する） ---
last_checked_time = None 
is_first_check_of_day = True
did_daily_tweet = False
JST = pytz.timezone('Asia/Tokyo')

# ★★★ 「初回起動」をチェックするためのファイル名 ★★★
FIRST_BOOT_FLAG_FILE = "first_boot.flag" # このファイルがあるかで初回起動を判断

# ----------------------------------------
# ★★★ 神ロジックの「核」！★★★
# (60秒に1回、この関数が動く)
# ----------------------------------------
@tasks.loop(seconds=60)
async def check_activity_loop():
    global last_checked_time, is_first_check_of_day, did_daily_tweet, JST, TARGET_CHANNEL_ID_STR, model
    
    try:
        # --- 日付リセット処理 ---
        now_for_reset = datetime.now(JST)
        if last_checked_time and last_checked_time.date() != now_for_reset.date():
            print(f"--- {now_for_reset.strftime('%Y-%m-%d')} ---")
            print("日付が変わりました！フラグをリセットします。")
            is_first_check_of_day = True
            did_daily_tweet = False
            last_checked_time = None 

        # --- 今が「浮上タイミング」か計算する ---
        now = datetime.now(JST)
        is_holiday = now.weekday() >= 5 # 土日か？
        
        target_hours = []
        if is_holiday:
            target_hours = [18, 19, 20, 21, 22, 23] # 休日: 18時～23時
        else:
            target_hours = [21, 22, 23] # 平日: 21時～23時
            
        if now.hour not in target_hours:
            # print(f"({now.strftime('%H:%M:%S')}) 浮上時間外です。") # デバッグ用
            last_checked_time = now
            return # 浮上時間じゃないなら何もしない
            
        # --- 浮上タイミング！（±5分ランダムをここでチェック） ---
        if now.minute >= 10:
            # print(f"({now.strftime('%H:%M:%S')}) {now.hour}時のチェック時間は過ぎました。") # デバッグ用
            return
            
        if last_checked_time and last_checked_time.hour == now.hour and last_checked_time.minute < 10:
            # print(f"({now.strftime('%H:%M:%S')}) {now.hour}時はもうチェック済みです。") # デバッグ用
            return

        # --- よっしゃ！浮上するぜ！ ---
        await asyncio.sleep(random.randint(1, 10)) # 1～10秒待つ
        
        print(f"--- ( {now.strftime('%Y-%m-%d %H:%M:%S')} ) ---")
        print(f"★★★ 浮上タイミング！ チェック開始！ ★★★")
        
        await bot.change_presence(status=discord.Status.online)
        
        # --- チャンネルIDが設定されてるかチェック（最重要） ---
        if not TARGET_CHANNEL_ID_STR:
            print("！！！エラー： TARGET_CHANNEL_ID が設定されていません。発言できません。")
            await bot.change_presence(status=discord.Status.invisible) # オフラインに戻る
            last_checked_time = now # チェック時間は記録
            return 
            
        try:
            target_channel_id_int = int(TARGET_CHANNEL_ID_STR)
            channel = bot.get_channel(target_channel_id_int) 
            if not channel:
                print(f"！！！エラー： チャンネルID ({TARGET_CHANNEL_ID_STR}) が見つかりません。")
                await bot.change_presence(status=discord.Status.invisible) # オフラインに戻る
                last_checked_time = now # チェック時間は記録
                return
        except Exception as e:
            print(f"！！！エラー： チャンネルIDが無効です。: {e}")
            await bot.change_presence(status=discord.Status.invisible) # オフラインに戻る
            last_checked_time = now # チェック時間は記録
            return

        # --- ここから発言ロジック ---
        
        # タイピング中にして「人間っぽさ」を出す
        async with channel.typing():
            await asyncio.sleep(random.randint(2, 5)) # 2～5秒タイピング中…

        # (ロジックC) 定時連絡（ロールプレイ）
        if is_first_check_of_day:
            print("[ロジックC] 今日初の浮上！受験生ツイートします。")
            # ★★★ 「可愛げ男子」設定に書き換え！ ★★★
            prompt = "君は「ハル」。受験期の男子高校生。口調はフレンドリーで可愛げがある（顔文字もたまに使う）。「塾終わったー疲れたー」みたいな感じの、日常ツイートを1個作って。（例：つかれたー（＞＜）"
            response = await model.generate_content_async(prompt) 
            await channel.send(response.text)
            is_first_check_of_day = False
            did_daily_tweet = True 

        # (ロジックC) 寝るツイート
        elif now.hour == 23: 
            print("[ロジックC] 23時だ！寝るツイートします。")
            # ★★★ 「可愛げ男子」設定に書き換え！ ★★★
            prompt = "君は「ハル」。受験期の男子高校生で、口調はフレンドリーで可愛げがある（顔文字もたまに使う）。「そろそろ寝るわー」みたいな感じの、おやすみツイートを1個作って。（例：も、限界（＞＜）おやすみー！）"
            response = await model.generate_content_async(prompt) 
            await channel.send(response.text)
            
        # (ロジックD) 日常ツイート（1日1回）
        elif not did_daily_tweet: 
            print("[ロジックD] 日常ツイートします。")
            # ★★★ 「可愛げ男子」設定に書き換え！ ★★★
            prompt = "君は「ハル」。受験期の男子高校生で、口調はフレンドリーで可愛げがある（顔文字もたまに使う）。「甘いもの食べたい」とか「今日寒いなー」みたいな、勉強とは関係ない何気ない日常ツイートを1個作って。"
            response = await model.generate_content_async(prompt)
            await channel.send(response.text)
            did_daily_tweet = True

        # (ロジックA) メンション確認
        print("[ロジックA] メンション確認します（まだ機能してません）")
        
        # (ロジックB) エゴサ確認
        print("[ロジックB] エゴサ確認します（まだ機能してません）")

        # --- チェック完了！ ---
        print("★★★ チェック完了！ オフラインに戻ります。★★★")
        
        await bot.change_presence(status=discord.Status.invisible)
        last_checked_time = now
        
    except Exception as e:
        print(f"！！！エラー：ループ処理中に何か起きました: {e}")
        await bot.change_presence(status=discord.Status.invisible)
        last_checked_time = now 


# ----------------------------------------
# Botが起動したときに呼ばれる処理
# ----------------------------------------
@bot.event
async def on_ready():
    global last_checked_time, JST, TARGET_CHANNEL_ID_STR, FIRST_BOOT_FLAG_FILE, model
    
    print(f'--- {bot.user} (ハル) がDiscordにログインしました ---')
    print('受験期モード、起動します...')

    # ----------------------------------
    # ★★★ 初回起動メッセージ（君のリクエスト！） ★★★
    # ----------------------------------
    if not TARGET_CHANNEL_ID_STR:
        print("！！！警告： TARGET_CHANNEL_ID が設定されてないため、初回起動メッセージは送れません。")
    else:
        if not os.path.exists(FIRST_BOOT_FLAG_FILE):
            print("★★★ 初回起動を検知！ ★★★")
            try:
                target_channel_id_int = int(TARGET_CHANNEL_ID_STR)
                channel = bot.get_channel(target_channel_id_int)
                if channel:
                    # ★★★ 「可愛げ男子」設定に書き換え！ ★★★
                    prompt = "君は「ハル」。受験期の男子高校生で、今日からこのDiscordサーバーに参加する。口調はフレンドリーで可愛げがある（顔文字もたまに使う）。『よろしく！』みたいな、初参加の挨拶を考えて。アイコンは趣味の女の子だけど、中身は男だからね！(・∀・)"
                    response = await model.generate_content_async(prompt) 
                    
                    async with channel.typing():
                        await asyncio.sleep(random.randint(2, 5))
                    
                    await channel.send(response.text)
                    print(f"初回起動メッセージを {channel.name} に送信しました。")
                    
                    with open(FIRST_BOOT_FLAG_FILE, 'w') as f:
                        f.write(datetime.now(JST).isoformat())
                    print(f"「{FIRST_BOOT_FLAG_FILE}」を作成しました。もう初回起動メッセージは送りません。")
                
                else:
                    print(f"！！！エラー： 初回起動メッセージを送るチャンネルID ({TARGET_CHANNEL_ID_STR}) が見つかりません。")
            
            except Exception as e:
                print(f"！！！エラー： 初回起動メッセージの送信に失敗しました: {e}")
        else:
            print(f"「{FIRST_BOOT_FLAG_FILE}」が存在するため、初回起動メッセージはスキップします。")

    # ----------------------------------

    last_checked_time = datetime.now(JST) - timedelta(days=1) 
    check_activity_loop.start()
    await bot.change_presence(status=discord.Status.invisible)

# ----------------------------------------
# Botを起動！
# ----------------------------------------
if DISCORD_TOKEN and GEMINI_API_KEY:
    try:
        print("「ハル」を起動します...")
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        print(f"！！！エラー：Botの起動に失敗しました。Discordトークンは合ってる？: {e}")
else:
    print("！！！エラー： DISCORD_TOKEN か GEMINI_API_KEY が .env (Secrets) に設定されていません。")
