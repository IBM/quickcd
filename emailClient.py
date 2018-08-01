import smtplib
from email.message import EmailMessage
from email.headerregistry import Address
from common import env


def sendEmail(subj, addrTuples, body):
    msg = EmailMessage()
    msg['Subject'] = subj
    msg['From'] = Address("quickcd", env.CD_EMAIL_ADDRESS)
    msg['To'] = [Address(name, email) for name, email in addrTuples]
    msg.set_content(body)
    with smtplib.SMTP(env.CD_SMTP_RELAY) as s:
        s.send_message(msg)
