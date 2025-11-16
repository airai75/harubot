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
intents.guilds = True # メンション確認のためにギルド情報が必要
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
last_checked_time = None       # 最後に「浮上」した時間
last_mention_check_time = None # 最後に「メンション」をチェックした時間
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
    global last_checked_time, is_first_check_of_day, did_daily_tweet, JST, TARGET_CHANNEL_ID_STR, model, last_mention_check_time
    
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

        # ----------------------------------
        # ★★★ ここからロジック！ ★★★
        # ----------------------------------
        
        # メンションやツイートで、もうこの浮上タイミングで発言したか？
        did_speak_in_this_float = False

        # (ロジックA) メンション確認 ★★★（ついに実装！）★★★
        # ----------------------------------
        print("[ロジックA] メンション確認します...")
        
        # JSTからUTCに変換（.history()はUTCを期待するため）
        # last_mention_check_time は on_ready で JST でセットされる
        check_after_time_utc = last_mention_check_time.astimezone(pytz.UTC)
        new_check_time_utc = now.astimezone(pytz.UTC) # 今この瞬間のUTC

        mentions_found = []
        try:
            # 履歴をさかのぼってメンションを探す
            async for message in channel.history(after=check_after_time_utc, before=new_check_time_utc, oldest_first=True):
                if bot.user in message.mentions:
                    mentions_found.append(message)
                    
        except Exception as e:
            print(f"！！！エラー： メンション履歴の取得に失敗しました: {e}")

        # メンションが見つかったら、1件だけ処理する
        if mentions_found:
            oldest_mention = mentions_found[0] # 一番古いメンション
            print(f"[ロジックA] メンション発見！ (from {oldest_mention.author.display_name})")
            
            # メンションの前3件の会話を「文脈」として取得
            context_log = ""
            try:
                context_messages = await channel.history(before=oldest_mention, limit=3, oldest_first=True).flatten()
                for ctx_msg in context_messages:
                    context_log += f"{ctx_msg.author.display_name}: {ctx_msg.content}\n"
            except Exception as e:
                print(f"！！！警告： メンション前の文脈取得に失敗: {e}")
                
            context_log += f"--- ここでメンション ---\n"
            context_log += f"{oldest_mention.author.display_name}: {oldest_mention.content}\n"
            
            # Geminiに「返事すべきか」聞く
            prompt = f"""【君の設定】
名前: ハル
性別: 男 (受験期)
口調: タメ口、フレンドリー、可愛げあり（例：(・∀・), ( ;∀;), （＞＜）)
プロフィール: 「受験期のためずっと反応できるわけじゃないです。メンションしてくれないと気づかない可能性もあります」

【ミッション】
以下の会話ログで、僕（ハル）宛てのメンションが来た。
設定になりきって、返事すべき内容（質問、会話の続き）なら、可愛げのある返事を考えて。
スルーすべき内容（「おつー」「おやすみ」等の挨拶、ただの相槌、独り言）なら、「スルー」とだけ言って。

【会話ログ】
{context_log}
"""
            response = await model.generate_content_async(prompt)
            
            if "スルー" not in response.text:
                print("[ロジックA] Geminiが「返事すべき」と判断。返信します。")
                async with channel.typing():
                    await asyncio.sleep(random.
