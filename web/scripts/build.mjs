import esbuild from "esbuild";
import crypto from "crypto";
import fs from "fs";
import path from "path";

const root = process.cwd();
const docsDir = path.resolve(root, "../docs");
const assetsDir = path.join(docsDir, "assets");
const publicDir = path.join(root, "public");

fs.rmSync(docsDir, { recursive: true, force: true });
fs.mkdirSync(assetsDir, { recursive: true });

await esbuild.build({
  entryPoints: [path.join(root, "src/main.jsx")],
  bundle: true,
  minify: true,
  sourcemap: false,
  outdir: assetsDir,
  entryNames: "app",
  loader: {
    ".css": "css"
  },
  define: {
    "process.env.NODE_ENV": '"production"'
  }
});

copyFileIfExists(path.join(publicDir, "papers.json"), path.join(docsDir, "papers.json"));
const assetVersion = assetVersionFor([
  path.join(assetsDir, "app.js"),
  path.join(assetsDir, "app.css")
]);

fs.writeFileSync(
  path.join(docsDir, "index.html"),
  `<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Daily Paper Digest</title>
    <link rel="stylesheet" href="./assets/app.css?v=${assetVersion}" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="./assets/app.js?v=${assetVersion}"></script>
  </body>
</html>
`,
  "utf-8"
);

fs.writeFileSync(path.join(docsDir, ".nojekyll"), "", "utf-8");

function copyFileIfExists(from, to) {
  if (fs.existsSync(from)) {
    fs.mkdirSync(path.dirname(to), { recursive: true });
    fs.copyFileSync(from, to);
  }
}

function assetVersionFor(files) {
  const hash = crypto.createHash("sha256");
  for (const file of files) {
    hash.update(fs.readFileSync(file));
  }
  return hash.digest("hex").slice(0, 12);
}
