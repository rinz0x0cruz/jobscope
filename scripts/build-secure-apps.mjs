// Build a self-contained, passphrase-encrypted applications page.
//
// Reads the passphrase from STDIN (never argv/env, so it can't leak into logs or
// process listings), AES-256-GCM encrypts the FULL un-redacted jobscope
// dashboard.json under a PBKDF2-SHA256 key, and inlines the ciphertext into
// apps-template.html. The output HTML is safe to host publicly:
// it is useless without the passphrase, which is only ever entered in the browser.
//
// usage:  <passphrase-on-stdin> | node build-secure-apps.mjs <dashboard.json> <template.html> <out.html|-> [out.json]
//
// Pass "-" as <out.html> to skip the standalone page and only write the [out.json]
// blob, which the SPA imports into its Applications tab (web/src/data).
import { readFileSync, writeFileSync } from "node:fs";
import crypto from "node:crypto";

function readStdin() {
  try { return readFileSync(0, "utf8"); } catch { return ""; }
}

const [, , dashPath, tplPath, outPath, outJsonPath] = process.argv;
if (!dashPath || !tplPath || !outPath) {
  console.error("usage: <passphrase-on-stdin> | node build-secure-apps.mjs <dashboard.json> <template.html> <out.html|-> [out.json]");
  process.exit(2);
}

const passphrase = readStdin().replace(/\r?\n$/, "");
if (!passphrase) { console.error("error: empty passphrase (pipe it via stdin)"); process.exit(2); }
if (passphrase.length < 8) { console.error("error: passphrase too short (use 8+ characters, longer is better)"); process.exit(2); }

const dash = JSON.parse(readFileSync(dashPath, "utf8"));
// Encrypt the ENTIRE un-redacted dashboard so unlocking swaps in everything the
// public build redacts: job descriptions, match rationale, referral contacts,
// and the applications board + funnel.
const payload = dash;
const plaintext = Buffer.from(JSON.stringify(payload), "utf8");

const iter = 210000;
const salt = crypto.randomBytes(16);
const iv = crypto.randomBytes(12);
const key = crypto.pbkdf2Sync(Buffer.from(passphrase, "utf8"), salt, iter, 32, "sha256");
const cipher = crypto.createCipheriv("aes-256-gcm", key, iv);
const ct = Buffer.concat([cipher.update(plaintext), cipher.final()]);
const tag = cipher.getAuthTag();

const blob = {
  v: 1,
  kdf: "PBKDF2-SHA256",
  iter,
  salt: salt.toString("base64"),
  iv: iv.toString("base64"),
  ct: Buffer.concat([ct, tag]).toString("base64"), // ciphertext + 16-byte GCM tag (WebCrypto layout)
};

const nRows = (dash.rows || []).length;
const nApps = (dash.applications || []).length;
const summary = `${nRows} role(s) + ${nApps} application(s) (${plaintext.length} bytes)`;
if (outPath !== "-") {
  const tpl = readFileSync(tplPath, "utf8");
  if (!tpl.includes("__ENC_BLOB__")) { console.error("error: template is missing the __ENC_BLOB__ placeholder"); process.exit(1); }
  writeFileSync(outPath, tpl.replace("__ENC_BLOB__", JSON.stringify(blob)));
  console.log(`encrypted ${summary} -> ${outPath}`);
}
if (outJsonPath) {
  writeFileSync(outJsonPath, JSON.stringify(blob));
  console.log(`encrypted ${summary} -> ${outJsonPath}`);
}
