/**
 * WhatsApp Bridge — Baileys + Express
 *
 * Expõe REST API (porta 7334) para o bot Python enviar mensagens.
 * Recebe mensagens do WhatsApp e faz POST no webhook Python (porta 7333).
 *
 * Env vars:
 *   BRIDGE_PORT   porta REST deste servidor (default: 7334)
 *   WEBHOOK_URL   URL do webhook Python (default: http://localhost:7333/webhook)
 *   AUTH_DIR      pasta onde salva sessão Baileys (default: ./auth)
 */

const {
    default: makeWASocket,
    useMultiFileAuthState,
    DisconnectReason,
    downloadMediaMessage,
    fetchLatestBaileysVersion,
} = require("@whiskeysockets/baileys");
const express = require("express");
const axios = require("axios");
const qrcode = require("qrcode");
const pino = require("pino");
const fs = require("fs");
const path = require("path");

const BRIDGE_PORT = parseInt(process.env.BRIDGE_PORT || "7334");
const WEBHOOK_URL = process.env.WEBHOOK_URL || "http://localhost:7333/webhook";
const AUTH_DIR = process.env.AUTH_DIR || path.join(__dirname, "auth");

const logger = pino({ level: "silent" });

let sock = null;
let qrString = null;
let connected = false;
let reconnectTimer = null;
const chatStore = new Map(); // jid → { jid, name }

// ─── WhatsApp connection ─────────────────────────────────────────────────────

async function connectToWhatsApp() {
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const { version } = await fetchLatestBaileysVersion();

    sock = makeWASocket({
        version,
        auth: state,
        logger,
        printQRInTerminal: true,
        generateHighQualityLinkPreview: false,
        syncFullHistory: false,
    });

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("chats.upsert", (chats) => {
        for (const chat of chats) {
            chatStore.set(chat.id, { jid: chat.id, name: chat.name || chat.subject || "" });
        }
    });
    sock.ev.on("chats.update", (updates) => {
        for (const upd of updates) {
            if (upd.id) {
                const existing = chatStore.get(upd.id) || { jid: upd.id, name: "" };
                chatStore.set(upd.id, { ...existing, name: upd.name || upd.subject || existing.name });
            }
        }
    });

    // debug: log all events
    const _origEmit = sock.ev.emit.bind(sock.ev);
    sock.ev.emit = (event, ...args) => {
        if (!["messages.upsert", "connection.update", "creds.update"].includes(event))
            console.log(`[ev] ${event}`);
        return _origEmit(event, ...args);
    };

    sock.ev.on("connection.update", async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            qrString = qr;
            console.log(`\n📱 QR disponível em: http://localhost:${BRIDGE_PORT}/qr\n`);
        }

        if (connection === "close") {
            connected = false;
            qrString = null;
            const code = lastDisconnect?.error?.output?.statusCode;
            const loggedOut = code === DisconnectReason.loggedOut;
            console.log(`Conexão encerrada (código ${code}). ${loggedOut ? "Deslogado." : "Reconectando em 5s..."}`);
            if (!loggedOut) {
                clearTimeout(reconnectTimer);
                reconnectTimer = setTimeout(connectToWhatsApp, 5000);
            }
        } else if (connection === "open") {
            connected = true;
            qrString = null;
            console.log("✅ WhatsApp conectado!");
        }
    });

    // JID do Meta AI — mensagens fromMe=true ou type!=notify precisam ser entregues
    const META_AI_JID = process.env.META_AI_JID || "718584497008509@s.whatsapp.net";

    sock.ev.on("messages.upsert", async ({ messages, type }) => {
        console.log(`messages.upsert type=${type} count=${messages.length}`);

        for (const msg of messages) {
            const jid = msg.key.remoteJid || "";
            const isMetaAI = jid === META_AI_JID || jid.startsWith("718584497008509");
            const msgKeys = msg.message ? Object.keys(msg.message) : [];
            console.log(`msg fromMe=${msg.key.fromMe} jid=${jid} hasMsg=${!!msg.message} type=${type} metaAI=${isMetaAI} msgType=${msgKeys.join(',')}`);

            // Entrega mensagens do Meta AI independente de fromMe ou type
            if (isMetaAI && msg.message) {
                await deliverMessage(msg);
                continue;
            }

            if (type !== "notify") continue;
            if (msg.key.fromMe) continue;
            if (!msg.message) continue;

            await deliverMessage(msg);
        }
    });
}

async function deliverMessage(msg) {
    const remoteJid = msg.key.remoteJid || "";
    const participant = msg.key.participant || remoteJid;
    const isGroup = remoteJid.endsWith("@g.us");
    const msgContent = msg.message || {};

    // Extrai texto
    let text = "";
    let messageType = "text";
    let media = null;

    if (msgContent.conversation) {
        text = msgContent.conversation;
    } else if (msgContent.extendedTextMessage) {
        text = msgContent.extendedTextMessage.text || "";
    } else if (msgContent.imageMessage) {
        text = msgContent.imageMessage.caption || "";
        messageType = "image";
        media = { type: "image", mimeType: msgContent.imageMessage.mimetype };
    } else if (msgContent.videoMessage) {
        text = msgContent.videoMessage.caption || "";
        messageType = "video";
        media = { type: "video", mimeType: msgContent.videoMessage.mimetype };
    } else if (msgContent.audioMessage) {
        messageType = "audio";
        media = { type: "audio", ptt: !!msgContent.audioMessage.ptt };
    } else if (msgContent.documentMessage) {
        text = msgContent.documentMessage.caption || "";
        messageType = "document";
        media = { type: "document", fileName: msgContent.documentMessage.fileName || "" };
    } else if (msgContent.stickerMessage) {
        messageType = "sticker";
        media = { type: "sticker" };
    } else if (msgContent.reactionMessage) {
        messageType = "reactionMessage";
    } else if (msgContent.buttonsResponseMessage) {
        text = msgContent.buttonsResponseMessage.selectedDisplayText || msgContent.buttonsResponseMessage.selectedButtonId || "";
        messageType = "buttonsResponse";
    } else if (msgContent.listResponseMessage) {
        text = msgContent.listResponseMessage.title || msgContent.listResponseMessage.singleSelectReply?.selectedRowId || "";
        messageType = "listResponse";
    }

    // ID da mensagem respondida (quoted)
    let quotedMsgId = "";
    const ctx = (
        msgContent.extendedTextMessage?.contextInfo ||
        msgContent.imageMessage?.contextInfo ||
        msgContent.videoMessage?.contextInfo ||
        msgContent.audioMessage?.contextInfo
    );
    if (ctx?.stanzaId) quotedMsgId = ctx.stanzaId;

    const payload = {
        event: "message",
        msgId: msg.key.id || "",
        chat: remoteJid,
        sender: participant,
        isGroup,
        pushName: msg.pushName || "",
        text,
        messageType,
        media,
        quotedMsgId,
        rawKey: msg.key,
        rawMessage: msg.message,
    };

    try {
        await axios.post(WEBHOOK_URL, payload, { timeout: 8000 });
    } catch (e) {
        console.error(`Webhook falhou: ${e.message}`);
    }
}

// ─── REST API ────────────────────────────────────────────────────────────────

const app = express();
app.use(express.json({ limit: "64mb" }));

function requireConnected(req, res, next) {
    if (!sock || !connected) {
        return res.status(503).json({ ok: false, error: "not connected" });
    }
    next();
}

app.get("/status", (req, res) => {
    const user = sock?.user;
    const jid  = user?.id || "";
    const number = jid.split(":")[0].split("@")[0];
    res.json({ ok: true, connected, hasQr: !!qrString, jid, number });
});

app.get("/qr", async (req, res) => {
    if (!qrString) {
        return res.status(404).send("<html><body><p>Sem QR no momento. Bot já conectado ou ainda iniciando.</p></body></html>");
    }
    const img = await qrcode.toDataURL(qrString);
    res.send(`<html><body style="display:flex;flex-direction:column;align-items:center;font-family:sans-serif"><h2>Escanear QR — Link Bot</h2><img src="${img}" style="width:300px"><p>Abra o WhatsApp → Dispositivos vinculados → Vincular dispositivo</p></body></html>`);
});

app.get("/qr.png", async (req, res) => {
    if (!qrString) return res.status(404).send("sem QR");
    const buf = await qrcode.toBuffer(qrString, { type: "png", width: 400, margin: 2 });
    res.setHeader("Content-Type", "image/png");
    res.send(buf);
});

app.get("/qr/text", (req, res) => {
    if (!qrString) {
        return res.status(404).json({ ok: false, error: "no qr" });
    }
    res.json({ ok: true, qr: qrString });
});

function buildQuoted(jid, quotedId) {
    if (!quotedId) return undefined;
    return { key: { id: quotedId, remoteJid: jid, fromMe: false }, message: { conversation: "" } };
}

app.post("/send/text", requireConnected, async (req, res) => {
    const { jid, text, quoted_id } = req.body;
    if (!jid || text == null) return res.status(400).json({ ok: false, error: "jid e text obrigatórios" });
    try {
        const opts = quoted_id ? { quoted: buildQuoted(jid, quoted_id) } : {};
        const result = await sock.sendMessage(jid, { text: String(text) }, opts);
        res.json({ ok: true, id: result?.key?.id || "" });
    } catch (e) {
        console.error(`send/text erro: ${e.message}`);
        res.status(500).json({ ok: false, error: e.message });
    }
});

app.post("/send/image", requireConnected, async (req, res) => {
    const { jid, base64, caption = "", mimeType = "image/jpeg", quoted_id } = req.body;
    if (!jid || !base64) return res.status(400).json({ ok: false, error: "jid e base64 obrigatórios" });
    try {
        const buf = Buffer.from(base64, "base64");
        const opts = quoted_id ? { quoted: buildQuoted(jid, quoted_id) } : {};
        const result = await sock.sendMessage(jid, { image: buf, caption, mimetype: mimeType }, opts);
        res.json({ ok: true, id: result?.key?.id || "" });
    } catch (e) {
        console.error(`send/image erro: ${e.message}`);
        res.status(500).json({ ok: false, error: e.message });
    }
});

app.post("/send/audio", requireConnected, async (req, res) => {
    const { jid, base64, ptt = false, mimetype = "audio/ogg; codecs=opus", quoted_id } = req.body;
    if (!jid || !base64) return res.status(400).json({ ok: false, error: "jid e base64 obrigatórios" });
    console.log(`send/audio → jid=${jid} ptt=${ptt} mime=${mimetype} size=${base64.length}`);
    try {
        const buf = Buffer.from(base64, "base64");
        const opts = quoted_id ? { quoted: buildQuoted(jid, quoted_id) } : {};
        const result = await sock.sendMessage(jid, { audio: buf, ptt: !!ptt, mimetype }, opts);
        console.log(`send/audio OK → id=${result?.key?.id} remoteJid=${result?.key?.remoteJid}`);
        res.json({ ok: true, id: result?.key?.id || "" });
    } catch (e) {
        console.error(`send/audio erro: ${e.message}`);
        res.status(500).json({ ok: false, error: e.message });
    }
});

app.post("/send/sticker", requireConnected, async (req, res) => {
    const { jid, base64, quoted_id } = req.body;
    if (!jid || !base64) return res.status(400).json({ ok: false, error: "jid e base64 obrigatórios" });
    try {
        const buf = Buffer.from(base64, "base64");
        const opts = quoted_id ? { quoted: buildQuoted(jid, quoted_id) } : {};
        const result = await sock.sendMessage(jid, { sticker: buf }, opts);
        res.json({ ok: true, id: result?.key?.id || "" });
    } catch (e) {
        console.error(`send/sticker erro: ${e.message}`);
        res.status(500).json({ ok: false, error: e.message });
    }
});

app.post("/send/reaction", requireConnected, async (req, res) => {
    const { jid, msgId, emoji, fromMe = false } = req.body;
    if (!jid || !msgId || !emoji) return res.status(400).json({ ok: false, error: "jid, msgId e emoji obrigatórios" });
    try {
        await sock.sendMessage(jid, {
            react: { text: emoji, key: { remoteJid: jid, fromMe: !!fromMe, id: msgId } },
        });
        res.json({ ok: true });
    } catch (e) {
        console.error(`send/reaction erro: ${e.message}`);
        res.status(500).json({ ok: false, error: e.message });
    }
});

app.post("/send/presence", requireConnected, async (req, res) => {
    const { jid, presence = "composing" } = req.body;
    if (!jid) return res.status(400).json({ ok: false, error: "jid obrigatório" });
    try {
        await sock.sendPresenceUpdate(presence, jid);
        res.json({ ok: true });
    } catch (e) {
        // Presence failures are non-critical
        res.json({ ok: false, error: e.message });
    }
});

app.post("/download/media", requireConnected, async (req, res) => {
    const { rawKey, rawMessage } = req.body;
    if (!rawKey || !rawMessage) return res.status(400).json({ ok: false, error: "rawKey e rawMessage obrigatórios" });
    try {
        const msg = { key: rawKey, message: rawMessage };
        const buf = await downloadMediaMessage(msg, "buffer", {}, { reuploadRequest: sock.updateMediaMessage });
        res.json({ ok: true, base64: buf.toString("base64") });
    } catch (e) {
        console.error(`download/media erro: ${e.message}`);
        res.status(500).json({ ok: false, error: e.message });
    }
});

app.get("/chats", requireConnected, (req, res) => {
    const list = Array.from(chatStore.values());
    res.json({ ok: true, count: list.length, chats: list });
});

// ─── Start ───────────────────────────────────────────────────────────────────

app.listen(BRIDGE_PORT, "0.0.0.0", () => {
    console.log(`🌉 WhatsApp Bridge rodando em http://localhost:${BRIDGE_PORT}`);
    console.log(`   Webhook Python: ${WEBHOOK_URL}`);
    connectToWhatsApp().catch(console.error);
});
