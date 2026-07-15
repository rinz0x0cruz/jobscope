// Encrypt / decrypt a file with AES-256-GCM under a PBKDF2-SHA256 key (same
// primitives as build-secure-apps.mjs). Used by the cloud refresh workflow to keep
// the jobscope SQLite DB encrypted at rest on the private `data` branch, and by the
// one-time local seed step. The key is read from $JOBSCOPE_DB_KEY (never argv, so it
// can't leak into logs / process listings) or, if unset, from STDIN.
//
// usage:
//   JOBSCOPE_DB_KEY=... node crypt-file.mjs encrypt <in> <out.enc>
//   JOBSCOPE_DB_KEY=... node crypt-file.mjs decrypt <in.enc> <out>
//
// On-disk layout (binary): magic(4)="JSDB" | ver(1)=1 | salt(16) | iv(12) | ciphertext | tag(16)
import { readFileSync, writeFileSync } from "node:fs";
import crypto from "node:crypto";

const MAGIC = Buffer.from("JSDB");
const ITER = 210000;
const HEADER = MAGIC.length + 1 + 16 + 12; // magic + ver + salt + iv
const TAG = 16;

function readKey() {
  const env = process.env.JOBSCOPE_DB_KEY;
  if (env) return env;
  try { return readFileSync(0, "utf8").replace(/\r?\n$/, ""); } catch { return ""; }
}

const [, , mode, inPath, outPath] = process.argv;
if (!["encrypt", "decrypt"].includes(mode) || !inPath || !outPath) {
  console.error("usage: JOBSCOPE_DB_KEY=... node crypt-file.mjs <encrypt|decrypt> <in> <out>");
  process.exit(2);
}
const key = readKey();
if (!key) { console.error("error: empty key (set $JOBSCOPE_DB_KEY or pipe it via stdin)"); process.exit(2); }
if (key.length < 12) { console.error("error: key too short (use 12+ characters; a long random string is best)"); process.exit(2); }

const input = readFileSync(inPath);

if (mode === "encrypt") {
  const salt = crypto.randomBytes(16);
  const iv = crypto.randomBytes(12);
  const dk = crypto.pbkdf2Sync(Buffer.from(key, "utf8"), salt, ITER, 32, "sha256");
  const cipher = crypto.createCipheriv("aes-256-gcm", dk, iv);
  const ct = Buffer.concat([cipher.update(input), cipher.final()]);
  const tag = cipher.getAuthTag();
  writeFileSync(outPath, Buffer.concat([MAGIC, Buffer.from([1]), salt, iv, ct, tag]));
  console.error(`encrypted ${input.length} byte(s) -> ${outPath}`);
} else {
  if (input.length < HEADER + TAG || !input.subarray(0, MAGIC.length).equals(MAGIC)) {
    console.error("error: not a JSDB-encrypted file (bad magic / too short)");
    process.exit(1);
  }
  if (input[MAGIC.length] !== 1) {
    console.error(`error: unsupported JSDB version ${input[MAGIC.length]}`);
    process.exit(1);
  }
  const salt = input.subarray(5, 21);
  const iv = input.subarray(21, 33);
  const tag = input.subarray(input.length - TAG);
  const ct = input.subarray(HEADER, input.length - TAG);
  const dk = crypto.pbkdf2Sync(Buffer.from(key, "utf8"), salt, ITER, 32, "sha256");
  const decipher = crypto.createDecipheriv("aes-256-gcm", dk, iv);
  decipher.setAuthTag(tag);
  let pt;
  try {
    pt = Buffer.concat([decipher.update(ct), decipher.final()]);
  } catch {
    console.error("error: decryption failed (wrong key or corrupt file)");
    process.exit(1);
  }
  writeFileSync(outPath, pt);
  console.error(`decrypted ${pt.length} byte(s) -> ${outPath}`);
}
