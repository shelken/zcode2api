const { JSDOM, VirtualConsole } = require('jsdom');
const SCENE = process.argv[2] || '11xygtvd';
const REGION = process.argv[3] || 'sgp';
const PREFIX = process.argv[4] || 'no8xfe';

const vc = new VirtualConsole();  // 静默 jsdom 噪声
const html = `<!DOCTYPE html><html><head></head><body>
<div id="cap"></div><button id="btn"></button>
<script src="https://o.alicdn.com/captcha-frontend/aliyunCaptcha/AliyunCaptcha.js"></script>
</body></html>`;

// 完整伪装 Chrome 的 UA —— FeiLin 风险引擎第一道检查，
// jsdom 默认 UA ("Mozilla/5.0 (darwin) AppleWebKit/537.36") 会被当成不是浏览器而 F001。
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';

const dom = new JSDOM(html, {
  url: 'https://zcode.z.ai/',
  runScripts: 'dangerously',
  resources: 'usable',
  pretendToBeVisual: true,
  virtualConsole: vc,
  beforeParse(window) {
    const nav = window.navigator;
    const redefine = (target, prop, value) => { try { Object.defineProperty(target, prop, { value, configurable: true, writable: true }); } catch(e){} };

    // === navigator 全面伪装（实证成功的关键：UA / platform / vendor / webdriver）===
    redefine(nav, 'userAgent', UA);
    redefine(nav, 'appVersion', '5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36');
    redefine(nav, 'platform', 'MacIntel');
    redefine(nav, 'vendor', 'Google Inc.');
    redefine(nav, 'vendorSub', '');
    redefine(nav, 'product', 'Gecko');
    redefine(nav, 'productSub', '20030107');
    redefine(nav, 'webdriver', false);
    redefine(nav, 'language', 'en-US');
    redefine(nav, 'languages', ['en-US', 'en']);
    redefine(nav, 'hardwareConcurrency', 8);
    redefine(nav, 'deviceMemory', 8);
    redefine(nav, 'maxTouchPoints', 0);
    redefine(nav, 'cookieEnabled', true);
    redefine(nav, 'onLine', true);
    redefine(nav, 'doNotTrack', null);
    // plugins / mimeTypes：模拟 Chrome 默认（PDF Viewer）
    const pdf = { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 1 };
    const plugins = { 0: pdf, length: 1, item: (i) => (i === 0 ? pdf : null), namedItem: (n) => (n === 'PDF Viewer' ? pdf : null) };
    redefine(nav, 'plugins', plugins);
    const mt = { 'application/pdf': { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' }, length: 1, item: () => null, namedItem: (n) => (['application/pdf'].includes(n) ? mt['application/pdf'] : null) };
    redefine(nav, 'mimeTypes', mt);

    // === window 伪装 ===
    redefine(window, 'chrome', { runtime: {}, app: { isInstalled: false }, csi: () => {}, loadTimes: () => {} });
    redefine(window, 'devicePixelRatio', 2);
    redefine(window, 'outerWidth', 1680); redefine(window, 'outerHeight', 921);
    redefine(window, 'innerWidth', 1680); redefine(window, 'innerHeight', 834);
    redefine(window, 'screenX', 0); redefine(window, 'screenY', 0);

    // WebGLRenderingContext / AudioContext / RTCPeerConnection / permissions stub
    redefine(window, 'WebGLRenderingContext', function WebGLRenderingContext(){});
    redefine(window, 'WebGL2RenderingContext', function WebGL2RenderingContext(){});
    redefine(window, 'AudioContext', function AudioContext(){ return { createOscillator:()=>({connect(){},start(){},stop(){},frequency:{value:0}}), createAnalyser:()=>({}), createGain:()=>({connect(){},gain:{value:0}}), destination:{}, close:()=>{}, sampleRate:44100, state:'running' }; });
    redefine(window, 'webkitAudioContext', window.AudioContext);
    redefine(window, 'OfflineAudioContext', function OfflineAudioContext(){ return { createOscillator:()=>({connect(){},start(){}}), createDynamicsCompressor:()=>({}), destination:{}, startRendering:()=>Promise.resolve(new Float32Array(0)), sampleRate:44100 }; });
    redefine(window, 'RTCPeerConnection', function RTCPeerConnection(){ this.createDataChannel = () => ({}); this.createOffer = () => Promise.resolve({}); this.setLocalDescription = () => Promise.resolve(); this.close = () => {}; });
    redefine(window, 'webkitRTCPeerConnection', window.RTCPeerConnection);
    redefine(window, 'permissions', { query: () => Promise.resolve({ state: 'granted' }) });
    redefine(window, 'Notification', function Notification(){}); redefine(window.Notification, 'permission', 'default');

    // matchMedia（按 prefers-color-scheme 返回）
    window.matchMedia = (q) => ({ matches: /prefers-color-scheme:\s*light/.test(q), media: q, onchange: null, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){}, dispatchEvent(){return false;} });

    // canvas / webgl 指纹桩：返回稳定值即可
    const proto = window.HTMLCanvasElement.prototype;
    proto.getContext = function (type) {
      if (/webgl/i.test(type)) return { canvas:this, getParameter:()=> 'Apple M3 Pro', getExtension:()=>null, getSupportedExtensions:()=>['WEBGL_debug_renderer_info'], getContextAttributes:()=>({}), getShaderPrecisionFormat:()=>({precision:23,rangeMin:127,rangeMax:127}) };
      return { canvas:this, fillRect(){}, clearRect(){}, getImageData:(x,y,w=1,h=1)=>({data:new Uint8ClampedArray(w*h*4)}), putImageData(){}, createImageData:(w=1,h=1)=>({data:new Uint8ClampedArray(w*h*4)}), setTransform(){}, transform(){}, drawImage(){}, save(){}, restore(){}, beginPath(){}, moveTo(){}, lineTo(){}, bezierCurveTo(){}, quadraticCurveTo(){}, closePath(){}, clip(){}, stroke(){}, fill(){}, arc(){}, rect(){}, ellipse(){}, translate(){}, scale(){}, rotate(){}, fillText(){}, strokeText(){}, measureText:(t)=>({width:(''+t).length*8}), createLinearGradient:()=>({addColorStop(){}}), createRadialGradient:()=>({addColorStop(){}}), createPattern:()=>({}), isPointInPath:()=>false, font:'10px sans-serif', textBaseline:'alphabetic', textAlign:'start', fillStyle:'#000', strokeStyle:'#000', globalAlpha:1, lineWidth:1, shadowBlur:0, shadowColor:'' };
    };
    proto.toDataURL = () => 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
    proto.toBlob = (cb) => cb && cb(null);
    // Worker 桩
    window.Worker = class { constructor(){} postMessage(){} terminate(){} addEventListener(){} removeEventListener(){} onmessage=null; onerror=null; };
    window.OffscreenCanvas = window.OffscreenCanvas || class { constructor(w,h){this.width=w;this.height=h;} getContext(){return proto.getContext.call(this);} };
  },
});
const { window } = dom;

function waitFor(cond, t = 12000) {
  return new Promise((res, rej) => {
    const s = Date.now();
    const i = setInterval(() => { let ok=false; try{ok=cond();}catch{} if(ok){clearInterval(i);res();} else if(Date.now()-s>t){clearInterval(i);rej(new Error('timeout'));} }, 80);
  });
}

(async () => {
  await waitFor(() => typeof window.initAliyunCaptcha === 'function');
  window.initAliyunCaptcha({
    SceneId: SCENE, mode: 'popup', region: REGION, prefix: PREFIX,
    element: '#cap', button: '#btn', captchaLogoImg: '', showErrorTip: false,
    getInstance: (inst) => { try { (inst.startTracelessVerification || inst.show).call(inst); } catch (e) { console.error('start', e.message); } },
    success: (param) => { console.log('VERIFY_PARAM=' + param); process.exit(0); },
    fail: () => process.exit(4),
    onError: () => process.exit(5),
  });
  setTimeout(() => process.exit(2), 25000);
})().catch(() => process.exit(3));