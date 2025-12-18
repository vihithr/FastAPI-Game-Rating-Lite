import asyncio
import smtplib
import os
from redmail import EmailSender

from app.config.constants import SITE_BASE_URL

# 本地发信：通过 VPS 上的 Postfix/Sendmail，连接 localhost:25，无需认证/加密
LOCAL_MAIL_HOST = os.getenv("STG_LOCAL_MAIL_HOST", "localhost")
LOCAL_MAIL_PORT = int(os.getenv("STG_LOCAL_MAIL_PORT", "25"))

# 设定站点发件人地址（从环境变量读取）
SENDER_ADDRESS = os.getenv("STG_SENDER_ADDRESS", "noreply@localhost")

mail_sender = EmailSender(
    host=LOCAL_MAIL_HOST,
    port=LOCAL_MAIL_PORT,
    username=None,
    password=None,
    use_starttls=False,
    cls_smtp=smtplib.SMTP,
)


async def send_password_reset_email(email: str, token: str) -> None:
    """
    发送密码重置邮件（使用 redmail）。

    :param email: 收件人邮箱
    :param token: 重置 token，将会拼接到前端重置页面 URL 上
    """
    base_url = SITE_BASE_URL.rstrip("/")
    reset_url = f"{base_url}/password-reset?token={token}"
    subject = "STG 社区 - 密码重置通知"

    # 简洁版 HTML，减少花哨布局，降低被拦截概率
    body = f"""
    <html>
      <body style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#111827;background-color:#f9fafb;">
        <div style="max-width:560px;margin:16px auto;padding:16px 20px;background:#ffffff;border:1px solid #e5e7eb;border-radius:6px;">
          <h2 style="margin:0 0 12px 0;font-size:18px;color:#111827;">STG 社区密码重置</h2>
          <p style="margin:0 0 8px 0;line-height:1.6;">
            您（或他人）请求重置 STG 社区账户密码。如果这不是您的操作，您可以忽略本邮件。
          </p>
          <p style="margin:12px 0;">
            请点击下面的链接在浏览器中重置密码（链接在一定时间后会失效）：
          </p>
          <p style="margin:8px 0;word-break:break-all;">
            <a href="{reset_url}" style="color:#1d4ed8;text-decoration:underline;">{reset_url}</a>
          </p>
          <p style="margin:16px 0 0 0;font-size:12px;color:#6b7280;">
            本邮件由系统自动发送，请勿直接回复。
          </p>
        </div>
      </body>
    </html>
    """

    # redmail 为同步接口，这里用线程池异步调用，保持调用方接口不变
    loop = asyncio.get_running_loop()

    def _send():
        mail_sender.send(
            subject=subject,
            receivers=[email],
            html=body,
            sender=SENDER_ADDRESS,
        )

    await loop.run_in_executor(None, _send)


