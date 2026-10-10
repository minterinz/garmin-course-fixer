// test_engine.mjs —— 抽取 HTML 里的 ENGINE 段，逐字节比对 JS 版与 Python 版纠偏结果，并测 GPX。
import fs from 'node:fs';

const ws = 'E:/我的文档/deepseek-harness/default-workspace';
const html = fs.readFileSync(ws + '/garmin-fix/佳明路书纠偏器.html', 'utf8');
const eng = html.split('// ===== ENGINE START =====')[1].split('// ===== ENGINE END =====')[0];
if (!eng || eng.length < 1000) throw new Error('engine 段抽取失败');
const src = eng + '\nexport { GCJ, fitScan, fitApply, gpxScan, gpxApply, fitCrc };\n';
const mod = await import('data:text/javascript;base64,' + Buffer.from(src, 'utf8').toString('base64'));

const cases = [
  ['230小河.fit.fit', '230小河.fit-WGS'],
  ['231新滇池绿道环滇.fit.fit', '231新滇池绿道环滇-WGS'],
  ['777骑行_1月_24.fit.fit', '777骑行_1月_24.fit-WGS'],
  ['环草海融创.fit', '环草海融创-WGS'],
  ['环草海融创_1.fit', '环草海融创_1-WGS'],
];
let allOk = true;
for (const [f, newName] of cases) {
  const a = new Uint8Array(fs.readFileSync(`${ws}/edge_courses/${f}`));
  const b = new Uint8Array(fs.readFileSync(`${ws}/edge_courses_fixed/${f}`));
  const { bytes, info } = mod.fitApply(a, mod.GCJ.gcj2wgs, newName);
  if (bytes.length !== b.length) { console.log(`${f}: ❌ 长度不一致 ${bytes.length} vs ${b.length}`); allOk = false; continue; }
  let diff = 0, first = -1;
  for (let i = 0; i < b.length; i++) if (bytes[i] !== b[i]) { diff++; if (first < 0) first = i; }
  console.log(`${f}: pairs=${info.pairs.length} 差异字节=${diff}${first >= 0 ? ' 首个@' + first : ''} ${diff === 0 ? '✅ 与 Python 版逐字节一致' : '❌'}`);
  if (diff !== 0) allOk = false;
  // 反向自检：纠偏后再加偏应回到原值
  const back = mod.fitApply(bytes, mod.GCJ.wgs2gcj, null).bytes;
  let d2 = 0;
  for (let i = 0; i < a.length; i++) if (back[i] !== a[i]) d2++;
  console.log(`   ↳ WGS→GCJ 回算差异字节=${d2}${d2 === 0 ? ' ✅ 往返一致' : ' （±1 量化误差可接受）'}`);
}

const gpx = fs.readFileSync('F:/Downloads/黄龙箐-哈马者环线.gpx', 'utf8');
const out = mod.gpxApply(gpx, mod.GCJ.wgs2gcj);
const p0 = mod.gpxScan(gpx), p1 = mod.gpxScan(out);
console.log(`\nGPX: 点数 ${p0.length} → ${p1.length}`);
console.log(`  原始首点 ${p0[0].lat},${p0[0].lon}`);
console.log(`  加偏首点 ${p1[0].lat},${p1[0].lon}   期望 25.0866680,102.7992979`);
console.log(`  首点误差 dLat=${(p1[0].lat - 25.0866680).toExponential(2)} dLon=${(p1[0].lon - 102.7992979).toExponential(2)}`);
console.log(`  gpx 文本长度 ${gpx.length} → ${out.length}`);
console.log(allOk ? '\n== FIT 全部逐字节一致 ==' : '\n== 存在差异，需排查 ==');
