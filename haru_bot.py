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
# ★★★ 権限（Intents）をちゃんと設定！ ★★★
intents = discord.Intents.default()
intents.messages = True         # メッセージの受信
intents.message_content = True  # ★★★ メッセージの内容を読む権限 (超重要！) ★★★
intents.guilds = True           # サーバー情報（チャンネル履歴とか）
intents.members = True          # メンバー情報（メンション確認とか）
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
        
        did_speak_in_this_float = False
        
        # --- ★★★ ロジック修正！：「初回浮上」でもメンション確認する！ ---

        # (ロジックA) メンション確認
        # ----------------------------------
        print("[ロジックA] メンション確認します...")
        
        check_after_time_utc = last_mention_check_time.astimezone(pytz.UTC)
        new_check_time_utc = now.astimezone(pytz.UTC) # 今この瞬間のUTC

        mentions_found = []
        try:
            async for message in channel.history(after=check_after_time_utc, before=new_check_time_utc, oldest_first=True):
                if bot.user in message.mentions:
                    mentions_found.append(message)
                    
        except Exception as e:
            print(f"！！！エラー： メンション履歴の取得に失敗しました: {e}")

        # メンションが見つかったら、1件だけ処理する
        if mentions_found:
            oldest_mention = mentions_found[0] # 一番古いメンション
            print(f"[ロジックA] メンション発見！ (from {oldest_mention.author.display_name})")
            
            context_log = ""
            try:
                context_messages = await channel.history(before=oldest_mention, limit=3, oldest_first=True).flatten()
                for ctx_msg in context_messages:
                    context_log += f"{ctx_msg.author.display_name}: {ctx_msg.content}\n"
            except Exception as e:
                print(f"！！！警告： メンション前の文脈取得に失敗: {e}")
                
            context_log += f"--- ここでメンション ---\n"
            context_log += f"{oldest_mention.author.display_name}: {oldest_mention.content}\n"
            
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
                
                # ★★★ タイピング時間延長！ ★★★
                async with channel.typing():
                    await asyncio.sleep(random.randint(10, 20))
                
                await channel.send(response.text)
                did_speak_in_this_float = True
            else:
                print("[ロジックA] Geminiが「スルーすべき」と判断しました。")
                
            last_mention_check_time = oldest_mention.created_at.astimezone(JST)

        else:
            print("[ロジックA] 新しいメンションはありませんでした。")
            last_mention_check_time = now
            
        
        # (ロジックB) エゴサ確認（10件チェック）
        # ----------------------------------
        # ※メンションに返事した浮上タイミングでは、エゴサはしない（人間っぽい）
        if not did_speak_in_this_float:
            print("[ロジックB] エゴサ確認（10件）します...")
            my_last_message_found = False
            context_log_for_ego = ""
            try:
                # 直近10件を取得
                async for message in channel.history(limit=10, oldest_first=True):
                    context_log_for_ego += f"{message.author.display_name}: {message.content}\n"
                    if message.author == bot.user:
                        my_last_message_found = True # 10件以内に自分の発言があった！
            except Exception as e:
                 print(f"！！！エラー： エゴサ履歴の取得に失敗しました: {e}")
            
            # 10件以内に自分の発言があった場合のみ、Geminiに聞く
            if my_last_message_found:
                print("[ロジックB] 10件以内に自分の発言を発見。Geminiに精査させます。")
                
                prompt = f"""【君の設定】
名前: ハル (受験期の男子)
口調: フレンドリー、可愛げあり（例：(・∀・)）

【ミッション】
以下の直近10件の会話ログで、僕（ハル）の発言（「ハル: ...」）があった。
その僕の発言の「直後」に、僕に言及してる（メンション無しで）と思われるメッセージがあったら、それに対する返事を考えて。
なければ「スルー」とだけ言って。

【会話ログ】
{context_log_for_ego}
"""
                response = await model.generate_content_async(prompt)
                
                if "スルー" not in response.text:
                    print("[ロジックB] Geminiが「返事すべき」と判断。返信します。")
                    
                    # ★★★ タイピング時間延長！ ★★★
                    async with channel.typing():
                        await asyncio.sleep(random.randint(10, 20))
                        
                    await channel.send(response.text)
                    did_speak_in_this_float = True
                else:
                    print("[ロジックB] Geminiが「スルーすべき」と判断しました。")
            else:
                print("[ロジックB] 10件以内に自分の発言はありませんでした。")


        # (ロジックC) 定時連絡（ロールプレイ）
        # ----------------------------------
        # ※メンションにもエゴサにも反応しなかった場合のみ、ツイートする
        if not did_speak_in_this_float:
            if is_first_check_of_day:
                print("[ロジックC] 今日初の浮上！受験生ツイートします。")
                prompt = "君は「ハル」。受験期の男子高校生。口調はフレンドリーで可愛げがある（顔文字もたまに使う）。「塾終わったー疲れたー」みたいな感じの、日常ツイートを1個作って。（例：つかれたー（＞＜）"
                
                # ★★★ タイピング時間延長！ ★★★
                async with channel.typing():
                    await asyncio.sleep(random.randint(10, 20))
                
                response = await model.generate_content_async(prompt) 
                await channel.send(response.text)
                did_speak_in_this_float = True # 発言したフラグ
                is_first_check_of_day = False  # 「初回」フラグをOFF
                did_daily_tweet = True       # 「日常」フラグもON
            
            elif now.hour == 23: 
                print("[ロジックC] 23時だ！寝るツイートします。")
                prompt = "君は「ハル」。受験期の男子高校生で、口調はフレンドリーで可愛げがある（顔文字もたまに使う）。「そろそろ寝るわー」みたいな感じの、おやすみツイートを1個作って。（例：も、限界（＞＜）おやすみー！）"
                
                # ★★★ タイピング時間延長！ ★★★
                async with channel.typing():
                    await asyncio.sleep(random.randint(10, 20))
                
                response = await model.generate_content_async(prompt)
                await channel.send(response.text)
                did_speak_in_this_float = True # 発言したフラグ
            
            elif not did_daily_tweet: 
                print("[ロジックD] 日常ツイートします。")
                prompt = "君は「ハル」。受験期の男子高校生で、口調はフレンドリーで可愛げがある（顔文字もたまに使う）。「甘いもの食べたい」とか「今日寒いなー」みたいな、勉強とは関係ない何気ない日常ツイートを1個作って。"
                
                # ★★★ タイピング時間延長！ ★★★
                async with channel.typing():
                    await asyncio.sleep(random.randint(10, 20))
                
                response = await model.generate_content_async(prompt)
                await channel.send(response.text)
                did_speak_in_this_float = True # 発言したフラグ
                did_daily_tweet = True

        # --- チェック完了！ ---
        if did_speak_in_this_float:
            print("★★★ 発言したので、オフラインに戻ります。★★★")
        else:
            print("★★★ 発言せず。オフラインに戻ります。★★★")
        
        await bot.change_presence(status=discord.Status.invisible)
        last_checked_time = now # 「浮上チェック」の時間は最後に更新
        
    except Exception as e:
        print(f"！！！エラー：ループ処理中に何か起きました: {e}")
        await bot.change_presence(status=discord.Status.invisible)
        last_checked_time = datetime.now(JST) # エラー時も時間は更新
        last_mention_check_time = datetime.now(JST) # エラー時も時間は更新


# ----------------------------------------
# Botが起動したときに呼ばれる処理
# ----------------------------------------
@bot.event
async def on_ready():
    global last_checked_time, JST, TARGET_CHANNEL_ID_STR, FIRST_BOOT_FLAG_FILE, model, last_mention_check_time
    
    print(f'--- {bot.user} (ハル) がDiscordにログインしました ---')
    print('受験期モード、起動します...')

    # ----------------------------------
    # ★★★ 初回起動メッセージ ★★★
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
                    prompt = "君は「ハル」。受験期の男子高校生で、今日からこのDiscordサーバーに参加する。口調はフレンドリーで可愛げがある（顔文字もたまに使う）。『よろしく！』みたいな、初参加の挨拶を考えて。アイコンは趣味の女の子だけど、中身は男だからね！(・∀・)"
                    
                    # ★★★ タイピング時間延長！ ★★★
                    async with channel.typing():
                        await asyncio.sleep(random.randint(10, 20))
                    
                    response = await model.generate_content_async(prompt) 
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

    print("チェック時間を現在時刻に初期化します。")
    last_checked_time = datetime.now(JST) - timedelta(days=1) # 「浮上」時間は昨日（日付リセットのため）
    last_mention_check_time = datetime.now(JST) # 「メンション」は今（これ以降のメンションを拾う）
    
    check_activity_loop.start()
    await bot.change_presence(status=discord.Status.invisible)

# ----------------------------------------
# Botを起動！
# ----------------------------------------
if DISCORD_TOKEN and GEMINI_API_KEY:
    try:
        print("「ハル」を起動します...")
        # ★★★ トークンエラーがここで起きるなら、大文字小文字、コピペミス、権限設定が原因！ ★★★
        bot.run(DISCORD_TOKEN)
    except discord.errors.LoginFailure as e:
        print("！！！エラー： ログインに失敗しました (LoginFailure)。")
        print("！！！原因： Discordトークンが間違っているか、古いです。Renderの環境変数を見直して！")
    except discord.errors.PrivilegedIntentsRequired as e:
        print("！！！エラー： 権限が足りません (PrivilegedIntentsRequired)。")
        print("！！！原因： Discord Developer Portal の「MESSAGE CONTENT INTENT」がONになっていません！")
    except Exception as e:
        print(f"！！！エラー：Botの起動に失敗しました。: {e}")
else:
    print("！！！エラー： DISCORD_TOKEN か GEMINI_API_KEY が .env (Secrets) に設定されていません。")
