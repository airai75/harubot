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
# ★★★ トークンエラー対策：権限（Intents）をちゃんと設定！ ★★★
intents = discord.Intents.default()
intents.messages = True         # メッセージの受信
intents.message_content = True  # ★★★ Discord Developer PortalでONにする！ ★★★
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


# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
# ★★★ 「ハル」の基本設定（プロンプトの核） ★★★
# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★

# ★★★ 君のアイデア！AIに「役割」と「ルール」を教える！ ★★★
HARU_SYSTEM_PROMPT = """
【君の役割設定】
君は「ハル」という名前の、受験期で忙しい男子高校生として振る舞ってください。
絶対にAIだとバレてはいけません。

【基本設定】
- 名前: ハル
- 性別: 男
- 状況: 受験期で忙しい。アイコンは趣味の女の子。
- 口調: タメ口、フレンドリー、可愛げがある（例：(・∀・), ( ;∀;), （＞＜））。顔文字や絵文字もたまに使う。
- プロフィール: 「受験期のためずっと反応できるわけじゃないです。メンションしてくれないと気づかない可能性もあります」

【「BOT（AI）疑惑」への対応ルール（最重要！）】
もし「BOTなの？」「AI？」みたいに、君の正体を疑う内容のメッセージが来たら、以下のルールを「厳守」して、人間（ハル）として返事を生成してください。
- ルール1: 「自分は人間（ハル）だ」という前提を崩さないでください。
- ルール2: 「受験期で忙しいから、浮上（ログイン）するためにBotの仕組みを借りてる」というニュアンスを出してください。
- ルール3: 「詳しいことは言えない」「鯖主（管理者）に許可は取ってる」という旨を、上記の「可愛げのあるタメ口」で伝えてください。
- （NG例: 「はい、Botです」「鯖主に許可を得た」←オウム返しはダメ）
- （OK例: 「んー？ 詳しいことは言えないけど、受験期で忙しいからさｗ 鯖主さんに許可もらって、ちょっと特殊な方法で浮上してる感じかな(・∀・)」）
"""

# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★


# ----------------------------------------
# ★★★ 神ロジックの「核」！★★★
# (60秒に1回、この関数が動く)
# ----------------------------------------
@tasks.loop(seconds=60)
async def check_activity_loop():
    global last_checked_time, is_first_check_of_day, did_daily_tweet, JST, TARGET_CHANNEL_ID_STR, model, last_mention_check_time, HARU_SYSTEM_PROMPT
    
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
        # (1回の浮上で、該当する処理を順番に「全部」やる！)
        # ----------------------------------

        # (ロジックC1) 「塾おわ」ツイート (初回浮上時のみ、最優先)
        # ----------------------------------
        if is_first_check_of_day:
            print("[ロジックC1] 今日初の浮上！「塾おわ」をツイートします。")
            
            # ★★★ プロンプト修正！ ★★★
            prompt = f"""{HARU_SYSTEM_PROMPT}

【ミッション】
今、君（ハル）はその日初めてDiscordに浮上しました。
「塾終わったー疲れたー」みたいな感じの、日常ツイートを1個、生成してください。
（例：つかれたー（＞＜）
"""
            
            async with channel.typing():
                await asyncio.sleep(random.randint(10, 20))
            
            response = await model.generate_content_async(prompt) 
            await channel.send(response.text)
            
            is_first_check_of_day = False  # 「初回」フラグをOFF
            did_daily_tweet = True       # 「日常」フラグもON
        
        # (ロジックA) メンション確認 (毎回やる)
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
            
            # ★★★ プロンプト修正！ ★★★
            prompt = f"""{HARU_SYSTEM_PROMPT}

【ミッション】
以下の会話ログで、君（ハル）宛てのメンションが来ました。
君の役割設定（特に「BOT疑惑への対応ルール」）に従って、以下の優先順位で返事を生成してください。

1.  **[BOT疑惑]** もし「BOT（ボット）なの？」「AI？」みたいに、君の正体を疑う内容だったら、「BOT疑惑への対応ルール」に従ってはぐらかす返事を生成してください。
2.  **[返事する]** もし（1）じゃなくて、返事すべき内容（質問、会話の続き）なら、可愛げのある返事を生成してください。
3.  **[スルー]** もし（1）でも（2）でもなく、スルーすべき内容（「おつー」「おやすみ」等の挨拶、ただの相槌、独り言）なら、「スルー」とだけ出力してください。

【会話ログ】
{context_log}
"""
            response = await model.generate_content_async(prompt)
            
            if "スルー" not in response.text:
                print("[ロジックA] Geminiが「返事すべき」と判断。返信します。")
                async with channel.typing():
                    await asyncio.sleep(random.randint(10, 20))
                await channel.send(response.text)
                
            last_mention_check_time = oldest_mention.created_at.astimezone(JST)

        else:
            print("[ロジックA] 新しいメンションはありませんでした。")
            last_mention_check_time = now
            
        
        # (ロジックB) エゴサ確認（10件チェック） (毎回やる)
        # ----------------------------------
        print("[ロジックB] エゴサ確認（10件）します...")
        my_last_message_found = False
        context_log_for_ego = ""
        try:
            # 直近10件を取得
            async for message in channel.history(limit=10, oldest_first=True):
                # ログにはbotの名前（ハル）を含める
                author_name = "ハル" if message.author == bot.user else message.author.display_name
                context_log_for_ego += f"{author_name}: {message.content}\n"
                if message.author == bot.user:
                    my_last_message_found = True # 10件以内に自分の発言があった！
        except Exception as e:
             print(f"！！！エラー： エゴサ履歴の取得に失敗しました: {e}")
        
        # 10件以内に自分の発言があった場合のみ、Geminiに聞く
        if my_last_message_found:
            print("[ロジックB] 10件以内に自分の発言を発見。Geminiに精査させます。")
            
            # ★★★ プロンプト修正！ ★★★
            prompt = f"""{HARU_SYSTEM_PROMPT}

【ミッション】
以下の直近10件の会話ログで、君（ハル）の発言（「ハル: ...」）がありました。
その君の発言の「直後」に、君に言及してる（メンション無しで）と思われるメッセージがあったら、君の役割設定（特に「BOT疑惑への対応ルール」）に従って、以下の優先順位で返事を生成してください。

1.  **[BOT疑惑]** もし「BOT（ボット）なの？」「AI？」みたいに、君の正体を疑う内容だったら、「BOT疑惑への対応ルール」に従ってはぐらかす返事を生成してください。
2.  **[返事する]** もし（1)じゃなくて、返事すべき内容なら、可愛げのある返事を生成してください。
3.  **[スルー]** もし（1）でも（2）でもなければ「スルー」とだけ出力してください。

【会話ログ】
{context_log_for_ego}
"""
            response = await model.generate_content_async(prompt)
            
            if "スルー" not in response.text:
                print("[ロジックB] Geminiが「返事すべき」と判断。返信します。")
                async with channel.typing():
                    await asyncio.sleep(random.randint(10, 20))
                await channel.send(response.text)
            else:
                print("[ロジックB] Geminiが「スルーすべき」と判断しました。")
        else:
            print("[ロジックB] 10件以内に自分の発言はありませんでした。")


        # (ロジックC2) 「寝る」ツイート (23時台のみ、最後にやる)
        # ----------------------------------
        if now.hour == 23: 
            print("[ロジックC2] 23時だ！寝るツイートします。")
            
            # ★★★ プロンプト修正！ ★★★
            prompt = f"""{HARU_SYSTEM_PROMPT}

【ミッション】
今、23時台になりました。
「そろそろ寝るわー」みたいな感じの、おやすみツイートを1個、生成してください。
（例：も、限界（＞＜）おやすみー！）
"""
            
            async with channel.typing():
                await asyncio.sleep(random.randint(10, 20))
            
            response = await model.generate_content_async(prompt)
            await channel.send(response.text)
        
        # (ロジックD) 「日常」ツイート (「塾おわ」してない浮上時のみ)
        # ----------------------------------
        elif not is_first_check_of_day and not did_daily_tweet: 
            print("[ロジックD] 日常ツイートします。")

            # ★★★ プロンプト修正！ ★★★
            prompt = f"""{HARU_SYSTEM_PROMPT}

【ミッション】
今日まだ「塾おわ」以外の日常的なツイートをしていません。
「甘いもの食べたい」とか「今日寒いなー」みたいな、勉強とは関係ない何気ない日常ツイートを1個、生成してください。
"""
            
            async with channel.typing():
                await asyncio.sleep(random.randint(10, 20))
            
            response = await model.generate_content_async(prompt)
            await channel.send(response.text)
            did_daily_tweet = True

        # --- チェック完了！ ---
        print("★★★ チェック完了！ オフラインに戻ります。★★★")
        
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
    global last_checked_time, JST, TARGET_CHANNEL_ID_STR, FIRST_BOOT_FLAG_FILE, model, last_mention_check_time, HARU_SYSTEM_PROMPT
    
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
                    
                    # ★★★ プロンプト修正！ ★★★
                    prompt = f"""{HARU_SYSTEM_PROMPT}
                    
【ミッション】
君（ハル）は、今日からこのDiscordサーバーに初めて参加しました。
『よろしく！』みたいな、初参加の挨拶を生成してください。
"""
                    
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
