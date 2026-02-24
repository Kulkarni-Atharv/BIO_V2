"""
scripts/simulate_dashboard.py
─────────────────────────────
Simulates the dashboard side of the MQTT employee sync.

What this does (matches staffAttendanceGetUsers.js exactly):
  1. Subscribes to  {username}/a/{device_id}/request-users   ← listens for CM4 trigger
  2. When CM4 publishes there, responds with employee list on:
              {username}/a/{device_id}/receive-users          ← CM4 picks this up

Run this on the laptop WHILE mqtt_sync.py is running on CM4.
You should see the CM4 logs show: "Upserted N users into local users table."

Usage:
  python scripts/simulate_dashboard.py
"""

import sys, os, json, time, ssl, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paho.mqtt.client as mqtt
from shared.config import (
    MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD,
    MQTT_TOPIC_REQUEST_USERS, MQTT_TOPIC_RECEIVE_USERS
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
logger = logging.getLogger("Dashboard_Sim")

# ── Sample employee list (edit this to match your real employees) ──────────────
EMPLOYEES = [
    {"user_id": "101", "name": "Atharv Kulkarni"},
    {"user_id": "102", "name": "Ravi Sharma"},
    {"user_id": "103", "name": "Manoj Patil"},
    {"user_id": "104", "name": "Priya Desai"},
]

# ── Topics ─────────────────────────────────────────────────────────────────────
LISTEN_TOPIC  = MQTT_TOPIC_REQUEST_USERS   # CM4 publishes here → we listen
RESPOND_TOPIC = MQTT_TOPIC_RECEIVE_USERS   # we publish here → CM4 listens

# ── Callbacks ──────────────────────────────────────────────────────────────────

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Dashboard Simulator connected to EMQX")
        logger.info("Listening on : %s", LISTEN_TOPIC)
        logger.info("Will respond : %s", RESPOND_TOPIC)
        client.subscribe(LISTEN_TOPIC, qos=1)
        logger.info("Subscribed OK. Waiting for CM4 request...")
    else:
        logger.error("Connection failed: rc=%d", rc)


def on_message(client, userdata, msg):
    logger.info("")
    logger.info("=== REQUEST received on: %s ===", msg.topic)

    try:
        raw = msg.payload.decode("utf-8")
        logger.info("Payload: %s", raw)
    except Exception:
        logger.info("(empty payload)")

    # Send employee list back to CM4
    response = json.dumps(EMPLOYEES)
    client.publish(RESPOND_TOPIC, response, qos=1)
    logger.info("Sent %d employees to: %s", len(EMPLOYEES), RESPOND_TOPIC)
    logger.info("Payload sent: %s", response)


def on_subscribe(client, userdata, mid, granted_qos):
    logger.info("Subscription confirmed (QoS=%s)", granted_qos)

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    client = mqtt.Client()
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    # TLS
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    client.tls_set_context(ctx)

    client.on_connect   = on_connect
    client.on_message   = on_message
    client.on_subscribe = on_subscribe

    logger.info("Connecting to %s:%s ...", MQTT_BROKER, MQTT_PORT)
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)

    logger.info("")
    logger.info("─────────────────────────────────────────")
    logger.info("  Dashboard Simulator running")
    logger.info("  Employees to send: %d", len(EMPLOYEES))
    for e in EMPLOYEES:
        logger.info("    [%s] %s", e["user_id"], e["name"])
    logger.info("─────────────────────────────────────────")
    logger.info("")

    # Also send immediately once (for testing without CM4 request)
    # Uncomment the line below to push the list right away:
    # client.loop_start(); time.sleep(2); on_message(client, None, type('M', (), {'topic': LISTEN_TOPIC, 'payload': b''})())

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        logger.info("Stopped.")
        client.disconnect()


if __name__ == "__main__":
    main()
