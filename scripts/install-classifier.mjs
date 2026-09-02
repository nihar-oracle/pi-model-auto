import { createHash } from "node:crypto";
import { createReadStream, createWriteStream } from "node:fs";
import { mkdir, rename, rm } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { finished } from "node:stream/promises";

const packageRoot = fileURLToPath(new URL("..", import.meta.url));
const modelRoot = join(packageRoot, "models", "complexity-classifier");
const releaseBase = "https://github.com/nihar-oracle/pi-model-auto/releases/download/classifier-v1";
const assets = [
  { name: "config.json", path: "config.json", sha256: "e2649f77e0c730e0e73a953efb0cacc390a5173a388944421bf8c66cde1905cc" },
  { name: "tokenizer.json", path: "tokenizer.json", sha256: "8eb3950859984c5e7062c5e94d8d8026df86a527a5b6015f1d06d1a89cebd5f4" },
  { name: "tokenizer_config.json", path: "tokenizer_config.json", sha256: "089ea75d6fd14ab0f1d2c12b0b1c8fdc6e52422ff584e0b08e3e75ddd51af35e" },
  { name: "special_tokens_map.json", path: "special_tokens_map.json", sha256: "ea97ecdbcc73713039d8d64dbb05e3689495c96657fbd9a18f5bed381be81049" },
  { name: "model_quantized.onnx", path: "onnx/model_quantized.onnx", sha256: "fc548045d5ce5d51c74b1b82b0c95daa511575135c9c49f9652b7a9b0a383343" },
];

async function digest(path) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest("hex");
}
let complete = true;
for (const asset of assets) {
  try {
    if (await digest(join(modelRoot, asset.path)) !== asset.sha256) complete = false;
  } catch {
    complete = false;
  }
}
if (complete) process.exit(0);

const stagingRoot = `${modelRoot}.tmp-${process.pid}`;
await rm(stagingRoot, { recursive: true, force: true });
try {
  for (const asset of assets) {
    const destination = join(stagingRoot, asset.path);
    await mkdir(dirname(destination), { recursive: true });
    const response = await fetch(`${releaseBase}/${asset.name}`, { redirect: "follow" });
    if (!response.ok || !response.body) throw new Error(`download failed for ${asset.name}: HTTP ${response.status}`);
    const output = createWriteStream(destination, { flags: "wx" });
    const hash = createHash("sha256");
    for await (const chunk of response.body) {
      hash.update(chunk);
      if (!output.write(chunk)) await new Promise((resolve) => output.once("drain", resolve));
    }
    output.end();
    await finished(output);
    const actual = hash.digest("hex");
    if (actual !== asset.sha256) throw new Error(`checksum mismatch for ${asset.name}: ${actual}`);
  }
  await rm(modelRoot, { recursive: true, force: true });
  await rename(stagingRoot, modelRoot);
  console.log("Installed pi-model-auto local complexity classifier");
} catch (error) {
  await rm(stagingRoot, { recursive: true, force: true });
  throw error;
}
