import smtplib
from email.message import EmailMessage
from flask import current_app


def send_email(to_email: str, subject: str, body: str) -> bool:
    """
    Envia email por SMTP (Office365). Si no hay credenciales configuradas,
    imprime el contenido en consola como fallback.
    """
    cfg = current_app.config

    username = cfg.get("MAIL_USERNAME")
    password = cfg.get("MAIL_PASSWORD")
    server = cfg.get("MAIL_SERVER")
    port = cfg.get("MAIL_PORT")
    use_tls = cfg.get("MAIL_USE_TLS")
    sender = cfg.get("MAIL_DEFAULT_SENDER") or username

    # Fallback si no está configurado
    if not username or not password:
        print("\n=== EMAIL FALLBACK (NO SMTP CONFIG) ===")
        print("TO:", to_email)
        print("SUBJECT:", subject)
        print("BODY:\n", body)
        print("=== END EMAIL FALLBACK ===\n")
        return False

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(server, port, timeout=20) as smtp:
            if use_tls:
                smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(msg)
        return True
    except Exception as e:
        # Si Office365 bloquea o hay error de credenciales, no rompemos el flujo.
        print("\n=== ERROR ENVIANDO EMAIL ===")
        print(e)
        print("=== FIN ERROR EMAIL ===\n")
        return False
