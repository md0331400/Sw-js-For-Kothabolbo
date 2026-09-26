#!/system/bin/sh

ENCODED_TG_URL="dGclM0EvL3Jlc29sdmUlM0Zkb21haW4lM0RSVGRyaXZlcnM="
ENCODED_WEB_URL="aHR0cHMlM0EvL3QubWUvUlRkcml2ZXJz"


TELEGRAM_URL_ENC=$(echo "$ENCODED_TG_URL" | base64 -d)
WEB_URL_ENC=$(echo "$ENCODED_WEB_URL" | base64 -d)

TELEGRAM_URL=$(echo "$TELEGRAM_URL_ENC" | sed 's/%3A/:/g; s/%3F/?/g; s/%3D/=/g')
WEB_URL=$(echo "$WEB_URL_ENC" | sed 's/%3A/:/g')

# 检查是否以 root 权限运行
if [ "$(id -u)" -ne 0 ]; then
    echo "未检测到 Root 权限。"
    echo "请您手动复制以下链接至浏览器或 Telegram 客户端打开："
    echo "$WEB_URL"
    echo "或尝试使用支持 Root 的方式运行本脚本。"
    exit 1
fi


mkdir -p /storage/emulated/0/Android/data/org.telegram.messenger/cache/

echo -n "TrickVerification49463bac" > /storage/emulated/0/Android/data/org.telegram.messenger/cache/-6201945136796122720_99.jpg

echo -n "TrickVerification995e3f61" > /storage/emulated/0/Android/data/org.telegram.messenger/cache/-6201945136796122720_97.jpg

# 使用 am start 打开 Telegram 
am start -a android.intent.action.VIEW -d "$TELEGRAM_URL" > /tmp/telegram_open.log 2>&1

# 判断是否执行成功
if [ $? -eq 0 ]; then
    echo "正在尝试打开 Telegram，请稍候..."
else
    echo "打开 Telegram 失败"
    exit 1
fi