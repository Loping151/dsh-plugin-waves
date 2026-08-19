// 浏览器端 bundle: dsh 按 exports["./client"] 整文件下发, 保持单文件(ModuleLoader 包装)

window.__ModuleLoader__.load({
  id: 'dsh-plugin-waves',
  factory: (require) => {
    var module = { exports: {} }
    var exports = module.exports
    const React = require('react')

    const API = '/waves-api'
    const CSS = `
.ww-card{display:flex;flex-direction:column;gap:8px;padding:8px 0;max-width:100%;min-width:0}
.ww-head{display:flex;align-items:center;gap:8px;font-size:12px;min-height:24px}
/* 卡面是深底描金的鸣潮风, 标签跟着走: 渐变金字 + 细金边 + 左侧竖条 */
.ww-title{flex:none;position:relative;font-size:11px;font-weight:800;letter-spacing:.14em;
  font-family:'Oswald',ui-sans-serif,system-ui,sans-serif;padding:3px 9px 3px 11px;border-radius:4px;
  background:linear-gradient(135deg,rgba(30,34,42,.92) 0%,rgba(15,17,21,.92) 100%);
  border:1px solid rgba(212,177,99,.34);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.06),0 1px 6px rgba(0,0,0,.28)}
.ww-title span{background:linear-gradient(180deg,#f4e3b4 0%,#d4b163 100%);
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.ww-title::before{content:"";position:absolute;left:3px;top:4px;bottom:4px;width:2px;border-radius:2px;
  background:linear-gradient(180deg,#f4e3b4,#d4b163);box-shadow:0 0 6px rgba(212,177,99,.55)}
.ww-cmd{font-family:ui-monospace,monospace;background:var(--dsw-alias-bg-l2,#2a2a2a);padding:2px 6px;
  border-radius:4px;opacity:.75;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.ww-head-gap{flex:1;min-width:8px}
.ww-text{white-space:pre-wrap;line-height:1.6;overflow-wrap:anywhere;word-break:break-word;max-width:100%;min-width:0}
.ww-img{max-width:100%;width:auto;align-self:flex-start;object-fit:contain;
  border-radius:8px;border:1px solid var(--dsw-alias-border-l1,#3a3a3a);cursor:zoom-in;
  transition:filter .15s}
.ww-img:hover{filter:brightness(1.06)}
.ww-shot{position:relative;align-self:flex-start;max-width:100%;line-height:0}
.ww-shot-tip{position:absolute;right:8px;bottom:8px;line-height:1;font-size:11px;padding:3px 7px;
  border-radius:999px;background:rgba(0,0,0,.55);color:#fff;opacity:0;transition:opacity .15s;
  pointer-events:none}
.ww-shot:hover .ww-shot-tip{opacity:1}
.ww-pending{height:0!important;overflow:hidden}
.ww-shot .ww-img{transition:opacity .18s}
/* 标题行右侧的一排工具: 同高同描边, 卡片 hover 时整组淡入 */
.ww-tools{flex:none;display:flex;align-items:center;gap:6px;opacity:0;transition:opacity .15s}
.ww-card:hover .ww-tools,.ww-tools:focus-within{opacity:1}
.ww-tool{flex:none;display:inline-flex;align-items:center;gap:6px;height:22px;padding:0 8px;
  box-sizing:border-box;font:inherit;font-size:11px;line-height:1;border-radius:6px;
  color:var(--dsw-alias-label-tertiary,#8b93a7);background:none;
  border:1px solid var(--dsw-alias-border-l3,rgba(128,140,170,.28));
  transition:color .15s,border-color .15s,background .15s}
button.ww-tool{cursor:pointer}
button.ww-tool:hover{color:var(--dsw-alias-label-primary,#e8eaf0);
  border-color:var(--dsw-alias-state-business-primary,#4176e6);
  background:var(--dsw-alias-interactive-bg-hover,rgba(128,140,170,.12))}
button.ww-tool[disabled]{cursor:progress}
.ww-tool input[type=range]{width:78px;height:2px;appearance:none;border-radius:999px;cursor:ew-resize;
  background:var(--dsw-alias-border-l3,rgba(128,140,170,.45))}
.ww-tool input[type=range]::-webkit-slider-thumb{appearance:none;width:10px;height:10px;border-radius:50%;
  cursor:ew-resize;background:var(--dsw-alias-state-business-primary,#4176e6);
  box-shadow:0 0 0 2px var(--dsw-alias-bg-l1,#1b1e24)}
.ww-tool input[type=range]::-moz-range-thumb{width:10px;height:10px;border:0;border-radius:50%;
  cursor:ew-resize;background:var(--dsw-alias-state-business-primary,#4176e6)}
.ww-fit-val{min-width:30px;text-align:right;font-variant-numeric:tabular-nums}
/* 缩放走 transform: iframe 内部不重排, 拖动时不闪。
   iframe 要保持整幅排版宽度, 不能被外层的 max-width:100% 夹窄, 否则右半边会被裁掉 */
.ww-frame-scale{overflow:hidden}
.ww-frame-scale .ww-frame{max-width:none;transform-origin:0 0}
.ww-lightbox{position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.86);
  display:flex;align-items:center;justify-content:center;overflow:auto;cursor:zoom-out}
.ww-lightbox img{display:block;margin:auto}
.ww-lightbox.fit img{max-width:96vw;max-height:94vh;object-fit:contain}
.ww-lightbox.raw{align-items:flex-start;justify-content:flex-start;cursor:zoom-in}
.ww-lightbox.raw img{max-width:none;max-height:none}
.ww-lb-bar{position:fixed;top:12px;right:16px;display:flex;gap:8px;z-index:10000}
.ww-lb-btn{font-size:12px;padding:5px 12px;border-radius:999px;cursor:pointer;color:#fff;
  border:1px solid rgba(255,255,255,.3);background:rgba(0,0,0,.5)}
.ww-lb-btn:hover{background:rgba(255,255,255,.16)}
.ww-frame-wrap{width:100%;line-height:0}
.ww-frame{max-width:100%;border:0;background:transparent;display:block;overflow:hidden;
  border-radius:8px;border:1px solid var(--dsw-alias-border-l1,#3a3a3a);color-scheme:normal}
.ww-btn{font-size:12px;padding:4px 10px;border-radius:999px;cursor:pointer;
  border:1px solid var(--dsw-alias-border-l1,#444);background:transparent;color:inherit}
.ww-btn:hover{background:var(--dsw-alias-interactive-bg-hover,#333)}
.ww-btn[disabled]{opacity:.5;cursor:progress}
.ww-quick{display:flex;flex-direction:column;gap:7px;padding-top:2px}
.ww-quick-head{display:flex;align-items:center;gap:6px;font-size:11px;line-height:1;
  letter-spacing:.02em;color:var(--dsw-alias-label-tertiary,#8b93a7)}
.ww-quick-dot{width:5px;height:5px;flex:none;border-radius:50%;
  background:var(--dsw-alias-state-business-primary,#4176e6);
  box-shadow:0 0 0 3px rgba(65,118,230,.18)}
.ww-btns{display:flex;flex-wrap:wrap;gap:8px}
.ww-chip{display:inline-flex;align-items:center;gap:6px;max-width:100%;box-sizing:border-box;
  font:inherit;font-size:12.5px;line-height:18px;padding:6px 13px 6px 10px;border-radius:999px;
  color:var(--dsw-alias-label-primary,#e8eaf0);cursor:pointer;
  border:1px solid var(--dsw-alias-border-l3,rgba(128,140,170,.28));
  background:var(--dsw-alias-interactive-bg-hover,rgba(128,140,170,.12));
  transition:background .15s,border-color .15s,box-shadow .15s,transform .12s}
.ww-chip:hover{transform:translateY(-1px);
  border-color:var(--dsw-alias-state-business-primary,#4176e6);
  background:var(--dsw-alias-interactive-bg-active,rgba(128,140,170,.2));
  box-shadow:0 3px 10px rgba(15,23,42,.16)}
.ww-chip:active{transform:translateY(0) scale(.97);box-shadow:none}
.ww-chip:focus-visible{outline:2px solid var(--dsw-alias-state-business-primary,#4176e6);
  outline-offset:2px}
.ww-chip-mark{flex:none;width:11px;text-align:center;font-family:ui-monospace,monospace;
  font-size:11px;color:var(--dsw-alias-label-tertiary,#8b93a7)}
.ww-chip:hover .ww-chip-mark{color:var(--dsw-alias-state-business-primary,#4176e6)}
.ww-chip-text{overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.ww-chip[disabled]{opacity:.45;cursor:default}
.ww-chip[disabled]:hover{transform:none;box-shadow:none;
  border-color:var(--dsw-alias-border-l3,rgba(128,140,170,.28));
  background:var(--dsw-alias-interactive-bg-hover,rgba(128,140,170,.12))}
.ww-chip[disabled]:hover .ww-chip-mark{color:var(--dsw-alias-label-tertiary,#8b93a7)}
.ww-chip.busy{opacity:1;cursor:progress;
  border-color:var(--dsw-alias-state-business-primary,#4176e6)}
.ww-chip.busy:hover{border-color:var(--dsw-alias-state-business-primary,#4176e6)}
.ww-spin{width:11px;height:11px;flex:none;box-sizing:border-box;border-radius:50%;
  border:1.5px solid var(--dsw-alias-state-business-primary,#4176e6);border-top-color:transparent;
  animation:ww-spin .7s linear infinite}
@keyframes ww-spin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){
  .ww-chip{transition:none}
  .ww-chip:hover{transform:none}
  .ww-spin{animation-duration:1.8s}
}
.ww-node{border-left:2px solid var(--dsw-alias-border-l1,#444);padding-left:10px;
  display:flex;flex-direction:column;gap:8px}
.ww-err{color:#e5534b;font-size:12px}
.ww-hint{font-size:11px;opacity:.55}
.ww-stale{display:flex;align-items:center;gap:10px}
.ww-set{display:flex;flex-direction:column;gap:22px;padding-bottom:8px}
.ww-set-group{display:flex;flex-direction:column;gap:2px}
.ww-set-title{font-size:14px;font-weight:600;padding:0 0 6px;
  border-bottom:1px solid var(--dsw-alias-border-l1,#444)}
.ww-set-row{display:flex;align-items:flex-start;gap:12px;padding:10px 0;
  border-bottom:1px solid var(--dsw-alias-border-l1,#3a3a3a)}
.ww-set-main{flex:1;min-width:0;display:flex;flex-direction:column;gap:3px}
.ww-set-label{font-size:13px;line-height:1.4}
.ww-set-desc{font-size:11px;opacity:.55;line-height:1.5;white-space:pre-wrap}
.ww-set-ctl{flex:none;width:240px;max-width:45%;display:flex;flex-direction:column;gap:4px;align-items:flex-end}
.ww-set-input,.ww-set-area{width:100%;box-sizing:border-box;font:inherit;font-size:12px;color:inherit;
  padding:5px 8px;border-radius:8px;border:1px solid var(--dsw-alias-border-l1,#444);
  background:var(--dsw-alias-bg-l2,#2a2a2a)}
.ww-set-area{min-height:66px;font-family:ui-monospace,monospace;resize:vertical}
.ww-set-switch{width:38px;height:22px;flex:none;border-radius:999px;cursor:pointer;padding:0;
  border:1px solid var(--dsw-alias-border-l1,#444);background:var(--dsw-alias-bg-l2,#2a2a2a);
  display:flex;align-items:center}
.ww-set-switch.on{background:#4c8dff;border-color:#4c8dff}
.ww-set-knob{width:16px;height:16px;border-radius:50%;background:#ddd;margin-left:2px;transition:margin .15s}
.ww-set-switch.on .ww-set-knob{margin-left:18px;background:#fff}
.ww-set-file{display:flex;align-items:center;gap:8px;width:100%;justify-content:flex-end}
.ww-set-file .name{flex:1;min-width:0;font-size:11px;opacity:.6;overflow:hidden;
  white-space:nowrap;text-overflow:ellipsis;direction:rtl;text-align:left}
.ww-up{flex:none;font-size:12px;padding:5px 12px;border-radius:8px;cursor:pointer;
  border:1px solid var(--dsw-alias-border-l1,#444);background:var(--dsw-alias-bg-l2,#2a2a2a)}
.ww-up:hover{border-color:var(--dsw-alias-state-business-primary,#4176e6)}
.ww-up input{display:none}
.ww-set-state{font-size:11px;opacity:.6}
.ww-set-state.ok{color:#3fb950;opacity:1}
.ww-set-state.err{color:#e5534b;opacity:1}
.ww-set-divider{margin:6px 0;border-top:1px dashed var(--dsw-alias-border-l1,#444);
  font-size:11px;opacity:.55;padding-top:6px}
`

    // 宽度上限(占会话区百分比), 取自服务配置; 图片和 HTML 卡片走同一套
    const LIMIT_KEY = 'ww-media-limits'
    let imgLimits = { portrait: 50, landscape: 75 }
    try {
      const cached = JSON.parse(localStorage.getItem(LIMIT_KEY) || 'null')
      if (cached && cached.portrait) imgLimits = cached
    } catch (e) {
      // 缓存坏了就用默认值, 等接口回来再纠正
    }
    fetch(API + '/api/config/media')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d && d.image_portrait_max_percent) {
          imgLimits = {
            portrait: d.image_portrait_max_percent,
            landscape: d.image_landscape_max_percent || 100,
          }
          try {
            localStorage.setItem(LIMIT_KEY, JSON.stringify(imgLimits))
          } catch (e) {
            // 存不下无所谓
          }
        }
      })
      .catch(() => {})

    // 同一条命令每次出的卡片尺寸基本不变: 记下来, 下次占位就按它留白, 不再从默认框跳一下
    const SIZE_KEY = 'ww-card-size'
    const SIZE_KEEP = 200
    let sizeMemo = null

    function allSizes() {
      if (sizeMemo) return sizeMemo
      try {
        sizeMemo = JSON.parse(localStorage.getItem(SIZE_KEY) || '{}')
      } catch (e) {
        sizeMemo = {}
      }
      return sizeMemo
    }

    function recallSize(key) {
      return key ? allSizes()[key] || null : null
    }

    function rememberSize(key, value) {
      if (!key) return
      const all = allSizes()
      const old = all[key]
      if (old && JSON.stringify(old) === JSON.stringify(value)) return
      all[key] = value
      const keys = Object.keys(all)
      if (keys.length > SIZE_KEEP) delete all[keys[0]]
      try {
        localStorage.setItem(SIZE_KEY, JSON.stringify(all))
      } catch (e) {
        // 存不下就只是下次还会跳一下
      }
    }

    // 高>宽算竖, 其余算横; 卡片和图片用同一判定
    function widthCap(width, height) {
      return height > width ? imgLimits.portrait : imgLimits.landscape
    }

    // 单张卡就地调宽; 数值就是它在会话区里占的宽度百分比。不写回配置, 只影响这一张
    function FitBar({ value, onChange }) {
      return React.createElement(
        'div',
        { className: 'ww-tool ww-fit-bar', onClick: (e) => e.stopPropagation() },
        React.createElement('input', {
          type: 'range',
          min: 25,
          max: 100,
          step: 5,
          value,
          title: '显示宽度',
          'aria-label': '显示宽度',
          onChange: (e) => onChange(Number(e.target.value)),
        }),
        React.createElement('span', { className: 'ww-fit-val' }, Math.round(value) + '%'),
      )
    }

    function download(url, filename) {
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.rel = 'noreferrer'
      document.body.appendChild(a)
      a.click()
      a.remove()
    }

    function safeName(text) {
      return (String(text || 'waves').replace(/[\\/:*?"<>|\s]+/g, '_').slice(0, 40)) || 'waves'
    }

    // 存一份到本地: HTML 卡片存服务端按原始宽度渲的截图, 图片存原图
    function SaveButton({ segments, label }) {
      const [busy, setBusy] = React.useState(false)
      const target = React.useMemo(() => firstMedia(segments), [segments])
      if (!target) return null

      const save = async () => {
        if (busy) return
        setBusy(true)
        const base = safeName(label)
        try {
          if (target.type === 'image') {
            download(API + target.url, base + target.url.slice(target.url.lastIndexOf('.')))
          } else {
            const name = target.url.slice(target.url.lastIndexOf('/') + 1)
            // 截图由服务端按原始设计宽度渲染, 首次要等一会儿
            const res = await fetch(API + '/api/media/' + name + '/png')
            if (!res.ok) throw new Error('截图失败 ' + res.status)
            const objectUrl = URL.createObjectURL(await res.blob())
            download(objectUrl, base + '.png')
            setTimeout(() => URL.revokeObjectURL(objectUrl), 10000)
          }
        } catch (e) {
          console.error('[waves] 保存失败', e)
        } finally {
          setBusy(false)
        }
      }

      return React.createElement(
        'button',
        {
          type: 'button',
          className: 'ww-tool',
          disabled: busy,
          title: target.type === 'image' ? '保存图片' : '保存为图片',
          onClick: save,
        },
        busy ? '保存中…' : '保存',
      )
    }

    // 一张卡里通常只有一个图/HTML, 保存按第一个来
    function firstMedia(segments) {
      for (const seg of segments || []) {
        if (!seg) continue
        if (seg.type === 'image' || seg.type === 'html') return seg
        if (seg.type === 'node') {
          const found = firstMedia(seg.items)
          if (found) return found
        }
      }
      return null
    }

    function CardTools({ segments, label, value, onChange }) {
      if (!hasMedia(segments)) return null
      return React.createElement(
        'div',
        { className: 'ww-tools' },
        React.createElement(FitBar, { value, onChange }),
        React.createElement(
          'button',
          {
            type: 'button',
            className: 'ww-tool',
            title: '恢复默认宽度',
            onClick: () => onChange(null),
          },
          '↺',
        ),
        React.createElement(SaveButton, { segments, label }),
      )
    }

    // 卡片里有图/HTML 才给滑块
    function hasMedia(segments) {
      return (segments || []).some(
        (seg) =>
          seg &&
          (seg.type === 'image' || seg.type === 'html' || (seg.type === 'node' && hasMedia(seg.items))),
      )
    }

    function ensureStyles() {
      let el = document.getElementById('ww-plugin-style')
      if (!el) {
        el = document.createElement('style')
        el.id = 'ww-plugin-style'
        el.setAttribute('data-plugin', 'dsh-plugin-waves')
        document.head.appendChild(el)
      }
      el.textContent = CSS
    }

    async function runCommand(command, opts) {
      const res = await fetch(API + '/api/chat', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          command,
          scene: (opts && opts.scene) || 'group',
          session_id: (opts && opts.sessionId) || 'dsh-ui',
        }),
      })
      if (!res.ok) throw new Error('请求失败 ' + res.status)
      return res.json()
    }

    function HtmlFrame({ url, onCommand, zoom, onCap, sizeKey }) {
      const wrapRef = React.useRef(null)
      const frameRef = React.useRef(null)
      const [dims, setDims] = React.useState(() => recallSize(sizeKey))
      const cap = dims ? widthCap(dims.w, dims.h) : 100
      React.useEffect(() => {
        if (dims && onCap) onCap(cap)
      }, [dims, cap, onCap])

      // 模板是固定宽度的: 告诉卡片可用宽度, 它等比缩放后回报精确尺寸, iframe 按内容定尺寸
      const pushWidth = React.useCallback(() => {
        const frame = frameRef.current
        const wrap = wrapRef.current
        if (!frame || !wrap || !frame.contentWindow) return
        const width = wrap.clientWidth
        if (width > 0) {
          frame.contentWindow.postMessage({ source: 'ww-host', kind: 'width', width }, '*')
        }
      }, [])

      React.useEffect(() => {
        function onMessage(e) {
          const data = e.data
          if (!data || typeof data !== 'object' || data.source !== 'ww-card') return
          const frame = frameRef.current
          if (frame && e.source !== frame.contentWindow) return
          if (data.kind === 'size' && typeof data.height === 'number') {
            const next = {
              w: Math.max(0, Math.min(data.width || 0, 4000)),
              h: Math.min(Math.max(data.height, 40), 20000),
            }
            rememberSize(sizeKey, next)
            // 只在尺寸真的变了才 setState, 避免桥的重复上报引起抖动
            setDims((prev) =>
              prev && prev.w === next.w && prev.h === next.h ? prev : next,
            )
          } else if (data.kind === 'ready') {
            pushWidth()
          } else if (data.kind === 'command' && data.command) {
            onCommand(data.command)
          }
        }
        window.addEventListener('message', onMessage)
        return () => window.removeEventListener('message', onMessage)
      }, [onCommand, pushWidth, sizeKey])

      React.useEffect(() => {
        const wrap = wrapRef.current
        if (!wrap || !window.ResizeObserver) return
        const observer = new ResizeObserver(pushWidth)
        observer.observe(wrap)
        return () => observer.disconnect()
      }, [pushWidth])

      // src 只认第一次: 切后台再回来时不重新加载, 避免重渲染闪烁
      const srcRef = React.useRef(API + url)
      // 卡片始终按整幅可用宽度排版(不重排、更清晰), 只改显示倍率; 百分比就是最终占宽
      const w = dims && dims.w > 0 ? dims.w : 0
      const h = dims ? dims.h : 320
      const percent = zoom === null || zoom === undefined ? cap : zoom
      const k = dims ? percent / 100 : 1
      return React.createElement(
        'div',
        { className: 'ww-frame-wrap', ref: wrapRef },
        React.createElement(
          'div',
          {
            className: 'ww-frame-scale' + (dims ? '' : ' ww-pending'),
            style: dims
              ? { width: Math.round(w * k) + 'px', height: Math.round(h * k) + 'px' }
              : { width: '100%' },
          },
          React.createElement('iframe', {
            ref: frameRef,
            className: 'ww-frame',
            src: srcRef.current,
            scrolling: 'no',
            style: {
              height: h + 'px',
              width: w ? w + 'px' : '100%',
              transform: k === 1 ? undefined : 'scale(' + k + ')',
            },
            sandbox: 'allow-scripts allow-same-origin',
            onLoad: pushWidth,
          }),
        ),
      )
    }

    function Lightbox({ src, onClose }) {
      const [raw, setRaw] = React.useState(false)

      React.useEffect(() => {
        function onKey(e) {
          if (e.key === 'Escape') onClose()
        }
        document.addEventListener('keydown', onKey)
        const prev = document.body.style.overflow
        document.body.style.overflow = 'hidden'
        return () => {
          document.removeEventListener('keydown', onKey)
          document.body.style.overflow = prev
        }
      }, [onClose])

      return React.createElement(
        'div',
        {
          className: 'ww-lightbox' + (raw ? ' raw' : ' fit'),
          onClick: onClose,
        },
        React.createElement(
          'div',
          { className: 'ww-lb-bar', onClick: (e) => e.stopPropagation() },
          React.createElement(
            'button',
            { className: 'ww-lb-btn', onClick: () => setRaw((v) => !v) },
            raw ? '适应窗口' : '原始大小',
          ),
          React.createElement(
            'a',
            { className: 'ww-lb-btn', href: src, target: '_blank', rel: 'noreferrer' },
            '新窗口',
          ),
          React.createElement('button', { className: 'ww-lb-btn', onClick: onClose }, '关闭'),
        ),
        React.createElement('img', {
          src,
          onClick: (e) => {
            e.stopPropagation()
            setRaw((v) => !v)
          },
        }),
      )
    }

    function ImageSegment({ url, zoom, onCap, sizeKey }) {
      const src = url.startsWith('/api/') ? API + url : url
      const [open, setOpen] = React.useState(false)
      const [box, setBox] = React.useState(() => recallSize(sizeKey))
      // 加载完才知道长宽: 用 aspect-ratio 固定占位, 避免图到位时页面跳动
      const onLoad = (e) => {
        const img = e.target
        const next = { cap: widthCap(img.naturalWidth, img.naturalHeight),
          ratio: img.naturalWidth + ' / ' + img.naturalHeight }
        rememberSize(sizeKey, next)
        setBox(next)
        if (onCap) onCap(next.cap)
      }
      const percent = zoom === null || zoom === undefined ? (box ? box.cap : 100) : zoom
      return React.createElement(
        'div',
        {
          className: 'ww-shot' + (box ? '' : ' ww-pending'),
          style: box ? { maxWidth: percent + '%', aspectRatio: box.ratio } : undefined,
        },
        React.createElement('img', {
          className: 'ww-img',
          src,
          onLoad,
          onClick: () => setOpen(true),
        }),
        React.createElement('span', { className: 'ww-shot-tip' }, '点击查看大图'),
        open && React.createElement(Lightbox, { src, onClose: () => setOpen(false) }),
      )
    }

    // 快捷指令: 一排胶囊, 点了当场转圈, 期间其余按钮压暗避免连点
    function ButtonsSegment({ rows, onCommand }) {
      const [busy, setBusy] = React.useState(-1)
      const alive = React.useRef(true)
      React.useEffect(() => () => {
        alive.current = false
      }, [])

      const items = []
      ;(rows || []).forEach((row) => {
        const list = Array.isArray(row) ? row : [row]
        list.forEach((btn) => {
          if (!btn) return
          const command = (btn.prefix || '') + (btn.data || btn.text || '')
          if (command) items.push({ label: btn.text || btn.data, command })
        })
      })
      if (!items.length) return null

      const fire = (item, index) => {
        if (busy >= 0) return
        setBusy(index)
        Promise.resolve(onCommand(item.command)).then(
          () => alive.current && setBusy(-1),
          () => alive.current && setBusy(-1),
        )
      }

      return React.createElement(
        'div',
        { className: 'ww-quick' },
        React.createElement(
          'div',
          { className: 'ww-quick-head' },
          React.createElement('span', { className: 'ww-quick-dot' }),
          React.createElement('span', null, '快捷指令'),
        ),
        React.createElement(
          'div',
          { className: 'ww-btns' },
          items.map((item, i) =>
            React.createElement(
              'button',
              {
                key: i,
                type: 'button',
                className: 'ww-chip' + (busy === i ? ' busy' : ''),
                disabled: busy >= 0,
                title: item.command,
                onClick: () => fire(item, i),
              },
              busy === i
                ? React.createElement('span', { className: 'ww-spin' })
                : React.createElement('span', { className: 'ww-chip-mark' }, '/'),
              React.createElement('span', { className: 'ww-chip-text' }, item.label),
            ),
          ),
        ),
      )
    }

    function Segment({ seg, onCommand, zoom, onCap, sizeKey }) {
      if (!seg) return null
      switch (seg.type) {
        case 'text':
          return React.createElement('div', { className: 'ww-text' }, seg.text)
        case 'image':
          return React.createElement(ImageSegment, { url: seg.url, zoom, onCap, sizeKey })
        case 'html':
          return React.createElement(HtmlFrame, { url: seg.url, onCommand, zoom, onCap, sizeKey })
        case 'node':
          return React.createElement(
            'div',
            { className: 'ww-node' },
            (seg.items || []).map((child, i) =>
              React.createElement(Segment, {
                key: i, seg: child, onCommand, zoom, onCap,
                sizeKey: sizeKey ? sizeKey + '.' + i : '',
              }),
            ),
          )
        case 'file':
          return React.createElement(
            'a',
            { href: API + seg.url, download: seg.name, className: 'ww-text' },
            '下载文件: ' + seg.name,
          )
        case 'buttons':
          return React.createElement(ButtonsSegment, { rows: seg.buttons, onCommand })
        default:
          return null
      }
    }

    // 卡片里点角色/按钮时再下一条命令, 结果追加在下方
    function useRunner(sessionId) {
      const [extras, setExtras] = React.useState([])
      const [pending, setPending] = React.useState(null)
      const [error, setError] = React.useState('')

      // 返回 promise, 让触发方(快捷指令胶囊)能显示自己的 loading
      const onCommand = React.useCallback((command) => {
        if (!command) return Promise.resolve()
        setPending(command)
        setError('')
        return runCommand(command, { sessionId })
          .then((data) => {
            const segs = (data && data.segments) || []
            setExtras((prev) => prev.concat([{ command, segments: segs }]))
          })
          .catch((e) => setError(String(e.message || e)))
          .finally(() => setPending(null))
      }, [sessionId])

      return { extras, pending, error, onCommand }
    }

    // 点出来的结果追加在下方; 新卡到位后把视口带过去, 不用手动往下翻
    function ExtraCard({ extra, onCommand, fresh }) {
      const ref = React.useRef(null)
      const [zoom, setZoom] = React.useState(null)
      const [cap, setCap] = React.useState(100)
      React.useEffect(() => {
        if (!fresh || !ref.current) return
        const id = requestAnimationFrame(() =>
          ref.current &&
          ref.current.scrollIntoView({ block: 'start', behavior: 'smooth' }),
        )
        return () => cancelAnimationFrame(id)
      }, [fresh])

      return React.createElement(
        'div',
        { className: 'ww-card', ref },
        React.createElement(
          'div',
          { className: 'ww-head' },
          React.createElement(
            'span',
            { className: 'ww-title' },
            React.createElement('span', null, 'XWUID'),
          ),
          React.createElement('span', { className: 'ww-cmd' }, extra.command),
          React.createElement('span', { className: 'ww-head-gap' }),
          React.createElement(CardTools, {
            segments: extra.segments,
            label: extra.command,
            value: zoom === null ? cap : zoom,
            onChange: setZoom,
          }),
        ),
        extra.segments.map((seg, j) =>
          React.createElement(Segment, {
            key: j, seg, onCommand, zoom, onCap: setCap,
            sizeKey: extra.command + '#' + j,
          }),
        ),
      )
    }

    function Extras({ extras, pending, error, onCommand }) {
      return React.createElement(
        React.Fragment,
        null,
        extras.map((extra, i) =>
          React.createElement(ExtraCard, {
            key: 'e' + i,
            extra,
            onCommand,
            fresh: i === extras.length - 1,
          }),
        ),
        pending && React.createElement('div', { className: 'ww-hint' }, '正在执行 ' + pending),
        error && React.createElement('div', { className: 'ww-err' }, error),
      )
    }

    // 图文没能还原(产物被清理/结果太老)时的兜底: 一行提示加重跑, 不铺裸链接
    function StaleResult({ text, onRerun }) {
      const [busy, setBusy] = React.useState(false)
      const rich = /已出图$/.test(String(text || ''))
      const run = () => {
        setBusy(true)
        Promise.resolve(onRerun()).then(
          () => setBusy(false),
          () => setBusy(false),
        )
      }
      if (!rich) return React.createElement('div', { className: 'ww-text' }, text)
      return React.createElement(
        'div',
        { className: 'ww-stale' },
        React.createElement('span', { className: 'ww-hint' }, '图文结果已不在缓存里'),
        React.createElement(
          'button',
          { type: 'button', className: 'ww-chip', disabled: busy, onClick: run },
          busy
            ? React.createElement('span', { className: 'ww-spin' })
            : React.createElement('span', { className: 'ww-chip-mark' }, '↻'),
          React.createElement('span', { className: 'ww-chip-text' }, '重新执行'),
        ),
      )
    }

    function WavesCard(props) {
      ensureStyles()
      const block = props.block || {}
      const args = block.arguments || block.args || {}
      const meta =
        (block.result && (block.result.meta || block.result.presentationMeta)) ||
        block.meta ||
        {}
      const initial = Array.isArray(meta.segments) ? meta.segments : []
      const runner = useRunner(props.callId)
      const [zoom, setZoom] = React.useState(null)
      const [cap, setCap] = React.useState(100)

      return React.createElement(
        'div',
        { className: 'ww-card' },
        React.createElement(
          'div',
          { className: 'ww-head' },
          React.createElement(
            'span',
            { className: 'ww-title' },
            React.createElement('span', null, 'XWUID'),
          ),
          React.createElement('span', { className: 'ww-cmd' }, String(args.command || '')),
          React.createElement('span', { className: 'ww-head-gap' }),
          React.createElement(CardTools, {
            segments: initial,
            label: String(args.command || ''),
            value: zoom === null ? cap : zoom,
            onChange: setZoom,
          }),
        ),
        initial.map((seg, i) =>
          React.createElement(Segment, {
            key: 'i' + i, seg, onCommand: runner.onCommand, zoom, onCap: setCap,
            sizeKey: String(args.command || '') + '#' + i,
          }),
        ),
        React.createElement(Extras, runner),
        !initial.length &&
          !runner.extras.length &&
          !runner.pending &&
          React.createElement('div', { className: 'ww-hint' }, '无展示内容'),
      )
    }

    // /ww 命令的行渲染: 结果图文按 commandId 从 host 内存取回, 取不到时退回文本
    function WavesCommandCard(props) {
      ensureStyles()
      const node = props.node || {}
      const outcome = node.outcome || null
      const commandId = node.commandId
      const settled = outcome ? outcome.kind : ''
      const [result, setResult] = React.useState(null)
      const [loaded, setLoaded] = React.useState(false)
      const [zoom, setZoom] = React.useState(null)
      const [cap, setCap] = React.useState(100)
      const runner = useRunner(props.sessionId)

      React.useEffect(() => {
        if (!commandId) return undefined
        let alive = true
        let timer = null
        let tries = 0
        // 结果由 host 在命令跑完后才落, 这里轮询到拿到为止(卡片挂载常早于结果)
        const poll = () => {
          fetch(API + '/host/results/' + encodeURIComponent(commandId))
            .then((res) => (res.ok ? res.json() : null))
            .then((data) => {
              if (!alive) return
              if (data && Array.isArray(data.segments)) {
                setResult(data)
                setLoaded(true)
                return
              }
              tries += 1
              if (tries > 150) {
                setLoaded(true)
                return
              }
              timer = setTimeout(poll, tries < 20 ? 400 : 1500)
            })
            .catch(() => {
              if (!alive) return
              tries += 1
              if (tries > 150) setLoaded(true)
              else timer = setTimeout(poll, 1500)
            })
        }
        poll()
        return () => {
          alive = false
          if (timer) clearTimeout(timer)
        }
      }, [commandId, settled])

      const label = String(node.args || '').trim() || node.name || 'ww'
      const segments = (result && result.segments) || []

      return React.createElement(
        'div',
        { className: 'ww-card' },
        React.createElement(
          'div',
          { className: 'ww-head' },
          React.createElement(
            'span',
            { className: 'ww-title' },
            React.createElement('span', null, 'XWUID'),
          ),
          React.createElement('span', { className: 'ww-cmd' }, '/' + (node.name || 'ww') + ' ' + label),
          !outcome && React.createElement('span', { className: 'ww-hint' }, '执行中…'),
          React.createElement('span', { className: 'ww-head-gap' }),
          React.createElement(CardTools, {
            segments, label, value: zoom === null ? cap : zoom, onChange: setZoom,
          }),
        ),
        settled === 'error' &&
          React.createElement('div', { className: 'ww-err' }, outcome.text || '执行失败'),
        segments.map((seg, i) =>
          React.createElement(Segment, {
            key: 'i' + i, seg, onCommand: runner.onCommand, zoom, onCap: setCap,
            sizeKey: label + '#' + i,
          }),
        ),
        settled === 'success' &&
          loaded &&
          !segments.length &&
          React.createElement(StaleResult, {
            text: outcome.text || '已执行',
            onRerun: () => runner.onCommand(label),
          }),
        React.createElement(Extras, runner),
      )
    }

    // ---- 设置页 ----

    function toText(value) {
      if (value === null || value === undefined) return ''
      if (Array.isArray(value)) return value.join(', ')
      if (typeof value === 'object') return JSON.stringify(value, null, 2)
      return String(value)
    }

    // 配置项 type + 值形态决定用哪种控件
    function controlOf(item) {
      const value = item.value
      if (item.type === 'Divider') return 'divider'
      // 纯上传项不给输入框; with_text 的(如头像)还留着填链接/QQ号的位置
      if (item.upload && !item.upload.with_text) return 'file'
      if (item.type === 'BoolConfig' || typeof value === 'boolean') return 'bool'
      if (item.type === 'IntConfig' || item.type === 'FloatConfig') {
        return item.options && item.options.length ? 'select' : 'number'
      }
      if (item.type === 'ListStrConfig' || item.type === 'ListConfig') return 'list'
      if (item.type === 'DictConfig') return 'json'
      if (typeof value === 'string') return 'text'
      if (typeof value === 'number') return 'number'
      if (value && typeof value === 'object') return 'json'
      return 'text'
    }

    // 落盘位置是写死的, 不给前端改; 只显示有没有、以及换一个
    function UploadButton({ item, onUpload }) {
      const suffix = (item.upload && item.upload.suffix) || ''
      return React.createElement(
        'label',
        { className: 'ww-up' },
        (item.upload && item.upload.exists ? '更换' : '上传') + (suffix ? ' .' + suffix : ''),
        React.createElement('input', {
          type: 'file',
          accept: suffix ? '.' + suffix : 'image/*',
          onChange: (e) => {
            const file = e.target.files && e.target.files[0]
            e.target.value = ''
            if (file) onUpload(item, file)
          },
        }),
      )
    }

    function FileControl({ item, onUpload }) {
      return React.createElement(
        'div',
        { className: 'ww-set-file' },
        React.createElement(
          'span',
          { className: 'name' },
          item.upload && item.upload.exists ? '已上传' : '未设置 · 用内置的',
        ),
        React.createElement(UploadButton, { item, onUpload }),
      )
    }

    function ConfigRow({ group, item, state, onSave, onFail, onUpload }) {
      const kind = controlOf(item)
      const secret = !!item.secret
      const [draft, setDraft] = React.useState(() => (secret ? '' : toText(item.value)))

      React.useEffect(() => {
        setDraft(secret ? '' : toText(item.value))
      }, [item.value, secret])

      const commit = React.useCallback(() => {
        if (secret) {
          if (!draft) return
          onSave(item, draft)
          setDraft('')
          return
        }
        if (draft === toText(item.value)) return
        if (kind === 'json') {
          let parsed
          try {
            parsed = JSON.parse(draft)
          } catch (e) {
            onFail(item, 'JSON 格式错误: ' + (e.message || e))
            return
          }
          onSave(item, parsed)
          return
        }
        onSave(item, draft)
      }, [draft, item, kind, secret, onSave, onFail])

      if (kind === 'divider') {
        return React.createElement(
          'div',
          { className: 'ww-set-divider' },
          item.value || item.title || '',
        )
      }

      const current = toText(item.value)
      let control
      if (kind === 'file') {
        control = React.createElement(FileControl, { item, onUpload })
      } else if (kind === 'bool') {
        const on = !!item.value
        control = React.createElement(
          'button',
          {
            type: 'button',
            className: 'ww-set-switch' + (on ? ' on' : ''),
            'aria-pressed': on ? 'true' : 'false',
            onClick: () => onSave(item, !on),
          },
          React.createElement('span', { className: 'ww-set-knob' }),
        )
      } else if (kind === 'select') {
        const options = (item.options || []).map(String)
        if (!options.includes(current)) options.unshift(current)
        control = React.createElement(
          'select',
          {
            className: 'ww-set-input',
            value: current,
            onChange: (e) => onSave(item, e.target.value),
          },
          options.map((opt) => React.createElement('option', { key: opt, value: opt }, opt)),
        )
      } else if (kind === 'json') {
        control = React.createElement('textarea', {
          className: 'ww-set-area',
          value: draft,
          spellCheck: false,
          onChange: (e) => setDraft(e.target.value),
          onBlur: commit,
        })
      } else {
        const listId = ('ww-dl-' + group + '-' + item.key).replace(/[^\w-]/g, '')
        const hasOptions = kind === 'text' && !secret && !!(item.options && item.options.length)
        control = React.createElement(
          React.Fragment,
          null,
          React.createElement('input', {
            className: 'ww-set-input',
            type: secret ? 'password' : kind === 'number' ? 'number' : 'text',
            value: draft,
            spellCheck: false,
            list: hasOptions ? listId : undefined,
            placeholder: secret ? current + ' · 输入新值覆盖' : kind === 'list' ? '逗号分隔' : '',
            onChange: (e) => setDraft(e.target.value),
            onBlur: commit,
            onKeyDown: (e) => {
              if (e.key === 'Enter') e.target.blur()
            },
          }),
          hasOptions &&
            React.createElement(
              'datalist',
              { id: listId },
              item.options.map((opt) =>
                React.createElement('option', { key: String(opt), value: String(opt) }),
              ),
            ),
        )
      }

      return React.createElement(
        'div',
        { className: 'ww-set-row' },
        React.createElement(
          'div',
          { className: 'ww-set-main' },
          React.createElement('div', { className: 'ww-set-label' }, item.title || item.key),
          item.desc && React.createElement('div', { className: 'ww-set-desc' }, item.desc),
        ),
        React.createElement(
          'div',
          { className: 'ww-set-ctl' },
          control,
          item.upload &&
            item.upload.with_text &&
            React.createElement(UploadButton, { item, onUpload }),
          state
            ? React.createElement('div', { className: 'ww-set-state ' + state.kind }, state.msg)
            : item.needs_restart &&
                React.createElement('div', { className: 'ww-set-state' }, '改后需重启生效'),
        ),
      )
    }

    function WavesSettings() {
      ensureStyles()
      const [groups, setGroups] = React.useState([])
      const [loading, setLoading] = React.useState(true)
      const [error, setError] = React.useState('')
      const [states, setStates] = React.useState({})

      React.useEffect(() => {
        let alive = true
        fetch(API + '/api/config')
          .then((res) => {
            if (!res.ok) throw new Error('请求失败 ' + res.status)
            return res.json()
          })
          .then((data) => {
            if (!alive) return
            setGroups((data && data.groups) || [])
            setLoading(false)
          })
          .catch((e) => {
            if (!alive) return
            setError(String(e.message || e))
            setLoading(false)
          })
        return () => {
          alive = false
        }
      }, [])

      const setState = React.useCallback((group, key, kind, msg) => {
        setStates((prev) => Object.assign({}, prev, { [group + '/' + key]: { kind, msg } }))
      }, [])

      const applyItem = React.useCallback((group, next) => {
        setGroups((prev) =>
          prev.map((g) =>
            g.name === group
              ? Object.assign({}, g, {
                  items: g.items.map((it) => (it.key === next.key ? next : it)),
                })
              : g,
          ),
        )
      }, [])

      const post = React.useCallback(
        (path, group, item, body, busyText, okText) => {
          setState(group, item.key, '', busyText)
          fetch(API + path, {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify(body),
          })
            .then(async (res) => {
              const data = await res.json().catch(() => null)
              if (!res.ok) {
                throw new Error((data && (data.detail || data.error)) || '请求失败 ' + res.status)
              }
              return data
            })
            .then((data) => {
              applyItem(group, data.item)
              setState(group, item.key, 'ok', data.needs_restart ? okText + ' · 重启后生效' : okText)
            })
            .catch((e) => setState(group, item.key, 'err', String(e.message || e)))
        },
        [applyItem, setState],
      )

      const save = React.useCallback(
        (group, item, value) =>
          post('/api/config', group, item, { group, key: item.key, value }, '保存中…', '已保存'),
        [post],
      )

      const upload = React.useCallback(
        (group, item, file) => {
          setState(group, item.key, '', '上传中…')
          const reader = new FileReader()
          reader.onerror = () => setState(group, item.key, 'err', '文件读取失败')
          reader.onload = () =>
            post(
              '/api/config/upload',
              group,
              item,
              { group, key: item.key, data: String(reader.result).split(',').pop() },
              '上传中…',
              '已上传',
            )
          reader.readAsDataURL(file)
        },
        [post, setState],
      )

      if (loading) return React.createElement('div', { className: 'ww-hint' }, '正在读取配置…')
      if (error) {
        return React.createElement('div', { className: 'ww-err' }, '配置读取失败: ' + error)
      }

      return React.createElement(
        'div',
        { className: 'ww-set' },
        groups.map((group) =>
          React.createElement(
            'div',
            { key: group.name, className: 'ww-set-group' },
            React.createElement('div', { className: 'ww-set-title' }, group.name),
            (group.items || []).map((item) =>
              React.createElement(ConfigRow, {
                key: item.key,
                group: group.name,
                item,
                state: states[group.name + '/' + item.key],
                onSave: (target, value) => save(group.name, target, value),
                onUpload: (target, file) => upload(group.name, target, file),
                onFail: (target, msg) => setState(group.name, target.key, 'err', msg),
              }),
            ),
          ),
        ),
      )
    }

    // ---- 斜杠命令接管 ----

    // dsh 的命令名只认 [a-z0-9_-] 且要空格收尾, /wwmr 会被当成命令名 wwmr、/ww深塔 直接不匹配,
    // 两者都落到模型。输入框的 enter 仲裁里认领所有 /ww 开头的行, 改写成 ww 命令当场执行。
    const SLASH = '/ww'
    // 前缀可配置(逗号分隔多个); 服务启动慢, 失败要重试而不是一锤定音
    let slashPrefixes = null
    let slashLoading = null
    // 前缀要等服务应答, 但槽位注册是同步的; 上次拿到的值缓存下来, 下次开页就能直接用
    const PREFIX_KEY = 'ww-slash-prefixes'

    function cachedPrefixes() {
      try {
        const list = JSON.parse(localStorage.getItem(PREFIX_KEY) || 'null')
        return Array.isArray(list) && list.length ? list : null
      } catch (e) {
        return null
      }
    }

    function loadPrefixes() {
      if (slashPrefixes) return Promise.resolve(slashPrefixes)
      if (slashLoading) return slashLoading
      slashLoading = fetch(API + '/api/health')
        .then((r) => r.json())
        .then((d) => {
          const list = (d && d.prefixes) || []
          if (list.length) {
            slashPrefixes = list.map((p) => '/' + String(p).toLowerCase())
            try {
              localStorage.setItem(PREFIX_KEY, JSON.stringify(slashPrefixes))
            } catch (e) {
              // 存不下就算了, 只是下次开页要再等一次请求
            }
          }
          return slashPrefixes
        })
        .catch(() => null)
        .finally(() => {
          slashLoading = null
        })
      return slashLoading
    }
    slashPrefixes = cachedPrefixes()
    loadPrefixes()

    // '/wwmr' '/xw深塔' → 'mr' '深塔'; 不是本插件的行给空串。
    // '/ww 查询' 这种带空格的 dsh 自己就认得, 这里必须放手, 否则会连着提交两遍。
    function wavesArgs(line, prefixes) {
      const text = String(line || '').trim()
      const lower = text.toLowerCase()
      for (const p of prefixes || slashPrefixes || [SLASH]) {
        if (!lower.startsWith(p)) continue
        const rest = text.slice(p.length)
        if (!rest || /^\s/.test(rest)) return ''
        return rest.trim()
      }
      return ''
    }

    // 空白新会话停在英雄页(composerPhase=blank), 斜杠命令会执行但对话区是 null,
    // 看起来像没响应; 发一句普通消息才会翻成会话。以前 return undefined 指望模型接手,
    // 但 dsh 自带的 command 源仍会认领 /ww, 英雄页翻不过去。所以自己认领执行,
    // 若仍是 blank 再补一次 prompt, 把界面拉起来。
    function sessionFace(sctx, sessionId) {
      try {
        const binding = sctx.sessions && sctx.sessions.binding(sessionId)
        return (binding && binding.session) || null
      } catch (e) {
        return null
      }
    }

    function sessionIsBlank(sctx, sessionId) {
      const face = sessionFace(sctx, sessionId)
      if (!face || typeof face.getSnapshot !== 'function') return false
      try {
        const snap = face.getSnapshot()
        return !!(snap && (snap.blank || snap.composerPhase === 'blank'))
      } catch (e) {
        return false
      }
    }

    async function kickstartIfBlank(sctx, sessionId) {
      const face = sessionFace(sctx, sessionId)
      if (!face || typeof face.prompt !== 'function') return
      if (!sessionIsBlank(sctx, sessionId)) return
      try {
        await face.prompt(
          [
            {
              type: 'text',
              text: '你好',
            },
          ],
          'queue',
        )
      } catch (e) {}
    }

    // 走 host 的命令执行, 结果照常落成命令流水节点, 由 WavesCommandCard 出卡片
    async function execCommand(ctx, sessionId, line) {
      const res = await ctx.remote.commands.execute(sessionId, line)
      if (!res || !res.ok) {
        const err = res && res.error
        throw new Error('鸣潮命令下发失败: ' + ((err && err.message) || '连接异常'))
      }
      if (!res.value) return { kind: 'error', text: '无法识别的命令: ' + line }
      return { kind: 'success' }
    }

    function isWavesCommandName(name) {
      const raw = String(name || '').toLowerCase()
      const prefixes = slashPrefixes || [SLASH]
      return prefixes.some((p) => raw === String(p).replace(/^\//, '').toLowerCase())
    }

    function registerKickstart(ctx) {
      ctx.inject(['sessions'], (sctx) => {
        sctx.effect(
          () =>
            sctx.on('command/executed', (sessionId, name) => {
              if (!isWavesCommandName(name)) return
              Promise.resolve(kickstartIfBlank(sctx, sessionId)).catch(() => {})
            }),
          'waves: 空白会话补 prompt',
        )
      })
    }

    function registerSlash(ctx) {
      ctx.inject(['inputTriggers', 'remote', 'remote.commands', 'sessions'], (sctx) => {
        sctx.effect(
          () =>
            sctx.inputTriggers.registerSource({
              trigger: '/',
              name: 'waves',
              // 候选菜单留给 dsh 自带的 command 源, 这里只接管 enter, 免得抢走回车
              candidates: () => Promise.resolve([]),
              onPick: () => undefined,
              matchEnter: async (session, line) => {
                let prefixes = slashPrefixes
                if (!prefixes) {
                  prefixes = await Promise.race([
                    loadPrefixes(),
                    new Promise((r) => setTimeout(() => r(null), 1500)),
                  ])
                }
                const args = wavesArgs(line, prefixes)
                if (!args) return undefined
                const submit = async (rest) => {
                  const out = await execCommand(
                    sctx,
                    session.sessionId,
                    SLASH + ' ' + ((rest && rest.trim()) || args),
                  )
                  await kickstartIfBlank(sctx, session.sessionId)
                  return out
                }
                const matched = (prefixes || slashPrefixes || [SLASH]).find((x) =>
                  line.toLowerCase().startsWith(x),
                )
                return { claim: { token: (matched || SLASH) + ' ', submit } }
              },
            }),
          'waves: 斜杠命令接管',
        )
      })
    }

    exports.inject = ['slots']
    exports.apply = (ctx) => {
      ensureStyles()
      registerSlash(ctx)
      registerKickstart(ctx)
      ctx.slots.inject('tool.call.toolview', () =>
        ctx.slots.register({ name: 'tool.call.toolview', key: 'waves' }, WavesCard),
      )
      ctx.slots.inject('settings.section', () =>
        ctx.slots.register(
          { name: 'settings.section', id: 'waves', order: 80, label: () => '鸣潮' },
          WavesSettings,
        ),
      )
      // 每个前缀都是一个命令名, 各自的结果卡都要挂。命令名对不上就会退回 dsh 的纯文本卡,
      // 所以前缀是异步取到的也得补注册, 不能只认注册那一刻的值。
      ctx.slots.inject('conversation.chat.commandview', () => {
        const offs = new Map()
        const add = (list) => {
          for (const item of list || []) {
            const key = String(item).replace(/^\//, '')
            if (!key || offs.has(key)) continue
            offs.set(
              key,
              ctx.slots.register(
                { name: 'conversation.chat.commandview', key },
                WavesCommandCard,
              ),
            )
          }
        }
        add(slashPrefixes || ['/ww'])
        loadPrefixes().then(add)
        return () => offs.forEach((off) => typeof off === 'function' && off())
      })
    }

    return module.exports
  },
})
