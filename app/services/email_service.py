import os
import resend

resend.api_key = (os.getenv("RESEND_API_KEY") or "").strip()


def send_verification_email(to_email: str, verify_url: str):
    from_email = (os.getenv("MAIL_DEFAULT_SENDER") or "").strip()

    if not resend.api_key:
        raise RuntimeError("RESEND_API_KEY no está configurada.")

    if not from_email:
        raise RuntimeError("MAIL_DEFAULT_SENDER no está configurado.")

    params: resend.Emails.SendParams = {
        "from": f"CoyoLabs <{from_email}>",
        "to": [to_email],
        "subject": "Verifica tu cuenta - Sistema de Laboratorios",
        "html": f"""
        <div style="font-family: Arial, sans-serif; color: #111; line-height: 1.6;">
            <h2 style="margin-bottom: 8px;">CoyoLabs</h2>
            <p>Hola.</p>
            <p>Para activar tu cuenta institucional, haz clic en el siguiente botón:</p>
            <p>
                <a href="{verify_url}"
                   style="display:inline-block;padding:12px 20px;background:#03A9F4;color:#fff;text-decoration:none;border-radius:8px;">
                   Verificar cuenta
                </a>
            </p>
            <p>Si el botón no funciona, abre este enlace:</p>
            <p><a href="{verify_url}">{verify_url}</a></p>
            <p>Este enlace expira en 1 hora.</p>
        </div>
        """,
        "text": (
            "Hola.\n\n"
            "Para activar tu cuenta institucional, abre este enlace:\n\n"
            f"{verify_url}\n\n"
            "Este enlace expira en 1 hora.\n"
        ),
    }

    return resend.Emails.send(params)