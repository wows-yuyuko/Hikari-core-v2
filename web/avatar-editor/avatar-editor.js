/* =========================================================
   Hikari 用户信息「预览 + 裁剪」组件  avatar-editor.js
   ---------------------------------------------------------
   两个可被任意设置页引入的独立组件（无依赖，不需要构建）：

     HikariUserPreview(containerEl, opts)
         预览 = 在 <iframe srcdoc> 里跑**真实的 v6 页面**
         （真 main-v6.css + avatar-v6.css + 真 DOM 结构 + ECharts），
         只在 contentDocument 里动态改 userInfo 那几个节点。
         用 iframe 是为了 CSS 完全隔离：v6 的 body{width:1500px} 之类
         不会漏到设置页上，设置页的样式也不会漏进预览。
         .render(userInfo)   —— 吃接口 /public/wows/account/search/db/{id}
                                返回的 data（顶层就是 userInfo 字段）；
                                传 {userInfo:{...}} 包装形式也认
         .getStageSize()     -> {w, h} 当前整页尺寸（大背景图裁剪要用）
         .setMode('fit'|'width')  缩放模式（默认 fit = 整页全览）
         .onModeChange = fn(mode) 模式切换回调
         .destroy()

     HikariImageCropper(containerEl, opts)
         固定缩放 + 平移不越界的取景裁剪器（对应模板的 background-position）
         .setFrame({w, h})      盒子在模板里的真实像素尺寸
         .setImage(src)         图片 URL / dataURL
         .setPosition(x, y)     背景位置百分比 0..100（缺省 50 = 居中）
         .getPosition()         -> {x, y}
         .reset()               回到居中
         .toDataURL(type, q)    导出裁剪结果（原图分辨率）
         .onChange = fn(pos)    拖动回调

   ▍模板里的槽位结构（三个图片槽位 + 两个文字槽位）
       slot = { status: 0|1, data: '<url 或文字>', dark: 0|1, crop?: {x, y} }
   ▍dark 在两个槽位里语义不同，别混用：
       banner.dark  = 0|1   深色标记（1 -> .dark-banner 白字）；只看 dark 值本身，
                            与 banner.status（显示开关）**无关**
       poster.dark  = 0-100 大背景图透明度（0 = 不透明 / 100 = 全透明，越大越淡）
   status 判断口径**完全照抄** partials/user-v6-macros.html，见 render() 注释。
   crop 是设置页附加的字段，模板侧不读它（宏写死 background-position: center）
   —— 想让模板也吃这个位置，见文件末尾说明。
   ========================================================= */
(function (global) {
    'use strict';

    /* 这套组件的版本标记 —— 改了 index.html / avatar-editor.js / avatar-editor.css
       里任何一处，就把时间顺手改一下（只要让页面能看出「刷新真的生效了」）。
       页面顶栏会显示它：改完代码刷新后时间没变，说明浏览器还在用缓存里的旧文件
       （Ctrl+F5 强制刷新即可）。
       （不走 ?v= 查询串是因为 file:// 下查询串会被当成文件名，直接加载失败。） */
    var HIKARI_BUILD = '2026-09-17 14:28';

    var STAGE_W = 1500;          // .page-box / .main-content 的固定宽度（main-v6.css）
    var PAGE_HEADER_W = 1400;    // 1500 - margin 50*2
    var PAGE_HEADER_H = 300;
    var AVATAR_BOX = 250;
    var DEFAULT_ASSET_BASE = '../../hikari_core/Template/';
    var AEP_UID = 0;             // 预览实例序号，用来给 postMessage 回执配对

    var SERVER_CN = {
        asia: '亚服', cn: '国服', eu: '欧服', na: '美服', ru: '俄服',
        sea: '东南亚服', jp: '日服', kr: '韩服'
    };

    function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }

    function num(v, dflt) {
        var n = parseInt(v, 10);
        return isNaN(n) ? (dflt || 0) : n;
    }

    function el(tag, cls, text) {
        var n = document.createElement(tag);
        if (cls) n.className = cls;
        if (text !== undefined && text !== null) n.textContent = text;
        return n;
    }

    function fmtTime(sec) {
        var s = Math.abs(num(sec, 0));
        if (!s) return 'N/A';
        var d = new Date(s * 1000);
        function p(v) { return v < 10 ? '0' + v : '' + v; }
        return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate())
            + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
    }

    function serverCn(u) {
        var v = (u && (u.serverCn || u.server)) || '';
        return SERVER_CN[v] || v || '未知';
    }

    /* 槽位取「背景位置」：crop 缺省 = 居中（等价模板的 background-position: center） */
    function cropPos(slot) {
        var c = slot && slot.crop;
        var x = c && typeof c.x === 'number' ? c.x : 50;
        var y = c && typeof c.y === 'number' ? c.y : 50;
        return clamp(x, 0, 100) + '% ' + clamp(y, 0, 100) + '%';
    }

    /* 槽位取「背景尺寸」：用户缩放过（crop.size 有值）就跟着它走，
       否则用模板原本的写法（头像/小背景 100%，大背景 cover）。 */
    function cropSize(slot, fallback) {
        var c = slot && slot.crop;
        return (c && c.size) ? c.size : fallback;
    }

    /* 大背景图（poster）的 dark。▍服务端口径（已对齐，别改）：值就是「透明度」
           0   = 完全不透明 → 背景图**完全显示**（最实，缺省）
           100 = 完全透明   → 背景图**完全看不见**
       中间线性。缺省 / 非数字按 0 兜底 —— 与 partials/*-v6-macros.html 里的
       `poster_img['dark'] | int` 缺省（0）保持同一口径，预览才不会和成品跑偏。
       注意 banner.dark 是另一回事（0/1 深色标记），别把它也丢进来。
       ▍posterDark() 返回 dark 原值（透明度）；要写进 CSS 的是 posterOpacity()
       —— CSS 的 opacity 是「不透明度」，与这里反着，换算只在 posterOpacity 里做。 */
    var POSTER_DARK_FALLBACK = 0;

    function posterDark(slot) {
        var raw = slot && slot.dark;
        if (raw === undefined || raw === null || raw === '') return POSTER_DARK_FALLBACK;
        var n = Number(raw);
        if (!isFinite(n)) return POSTER_DARK_FALLBACK;
        return clamp(Math.round(n), 0, 100);
    }

    /* dark（透明度）-> CSS 不透明度。两套语义是反的，转换**只在这里**做一次，
       别散落到各处 —— 模板侧的 `100 - poster_dark` 也是同一个意思。 */
    function posterOpacity(slot) {
        return 100 - posterDark(slot);
    }

    /* 遮罩 alpha = (100 - 不透明度) / 200，固定两位小数。
       ▍这里**必须**用 floor（截断）而不是 toFixed 的银行家舍入：
       模板侧走的是 Jinja 的整数除法，会截断（不透明度 = 93 时
       (100-93)*100/200 = 3.5 落到 3，即 0.03）。如果 JS 这边四舍五入成 0.04，
       预览就会比成品暗一档 —— 数值虽小，但两个渲染路径必须严格同构，
       否则「预览即成品」这个前提就破了。
       用 floor 前先消掉浮点误差（3.5 这类值虽然精确，但 0.05 之流二进制表示
       会有尾巴，所以统一先放大成整数再截断）。 */
    function posterMaskAlpha(opacity) {
        var pct = Math.floor((100 - opacity) * 100 / 200 + 1e-9);  // 百分位的整数
        var whole = Math.floor(pct / 100);
        var frac = String(pct % 100);
        if (frac.length < 2) frac = '0' + frac;
        return whole + '.' + frac;
    }

    /* =====================================================
       预览骨架：**真实 v6 渲染产物的结构**
       取自 tests/data/wows-yuyuko/temp_image/me.html（wws-info-v6 渲染结果），
       真类名、真内容块、真 ECharts 配置，只把 userInfo 那几个节点留空壳，
       由 render() 填。CSS 走 assetBase 指向的真实 v6 样式表
       —— 所以预览长什么样，机器人渲染出来就长什么样。
       ===================================================== */
    function buildFixture(base, uid) {
        return '<!DOCTYPE html>\n'
+ '<html lang="zh-cn">\n'
+ '<head>\n'
+ '<meta charset="utf-8">\n'
+ '<link href="' + base + 'main-v6.css" rel="stylesheet" type="text/css">\n'
+ '<link href="' + base + 'avatar-v6.css" rel="stylesheet" type="text/css">\n'
+ '<style id="aep-dyn"></style>\n'
+ '</head>\n'
+ '<body>\n'
+ '<div class="main-content">\n'
+ '    <div class="page-box">\n'
+ '\n'
+ '        <div class="page-header">\n'
+ '            <div class="masking-header">\n'
+ '                <div class="avatar-header"></div>\n'
+ '                <div class="clan-user-server">\n'
+ '                    <div class="user-info"><span class="aep-tag"></span><span class="mirage-text"></span></div>\n'
+ '                    <div class="user-account"></div>\n'
+ '                    <div class="user-server"></div>\n'
+ '                    <div class="user-sign-time"></div>\n'
+ '                    <div class="user-signature"></div>\n'
+ '                </div>\n'
+ '            </div>\n'
+ '        </div>\n'
+ '\n'
+ '        <div class="pr" style="background: #00BCD4;">\n'
+ '            <div class="svg-waves">\n'
+ '                <svg viewBox="0 0 500 200" preserveAspectRatio="none">\n'
+ '                    <path class="wave-path" d="M0,100 C150,200 350,0 500,100 L500,200 L0,200 Z"></path>\n'
+ '                </svg>\n'
+ '            </div>\n'
+ '            <span class="pr-number">1868\n'
+ '                <span class="pr-text">非常好</span></span>\n'
+ '        </div>\n'
+ '\n'
+ '        <div class="recnet-time">\n'
+ '            <span class="time-item">最后战斗时间：2026-09-11 22:08</span>\n'
+ '        </div>\n'
+ '\n'
+ '        <div class="overview-change">\n'
+ '            <div class="overview-change-item">\n'
+ '                <div class="item-top one-background-color">\n'
+ '                    <div class="stat-label">场次</div>\n'
+ '                    <div class="stat-value">9,830</div>\n'
+ '                </div>\n'
+ '                <div class="item-bottom">\n'
+ '                    <div class="bottom-mini-item one-background-color">\n'
+ '                        <div class="mini-label">加成经验</div>\n'
+ '                        <div class="mini-value">2,295</div>\n'
+ '                    </div>\n'
+ '                    <div class="bottom-mini-item one-background-color">\n'
+ '                        <div class="mini-label">命中率</div>\n'
+ '                        <div class="mini-value">34.45%</div>\n'
+ '                    </div>\n'
+ '                </div>\n'
+ '            </div>\n'
+ '            <div class="overview-change-item">\n'
+ '                <div class="item-top one-background-color">\n'
+ '                    <div class="stat-label">胜率</div>\n'
+ '                    <div class="stat-value" style="color: #673ab7;">63.53%</div>\n'
+ '                </div>\n'
+ '                <div class="item-bottom">\n'
+ '                    <div class="bottom-mini-item one-background-color">\n'
+ '                        <div class="mini-label">存活率</div>\n'
+ '                        <div class="mini-value">63.7%</div>\n'
+ '                    </div>\n'
+ '                    <div class="bottom-mini-item one-background-color">\n'
+ '                        <div class="mini-label">击落</div>\n'
+ '                        <div class="mini-value">6.00</div>\n'
+ '                    </div>\n'
+ '                </div>\n'
+ '            </div>\n'
+ '            <div class="overview-change-item">\n'
+ '                <div class="item-top one-background-color">\n'
+ '                    <div class="stat-label">场均</div>\n'
+ '                    <div class="stat-value" style="color: #A00DC5;">96,775</div>\n'
+ '                </div>\n'
+ '                <div class="item-bottom">\n'
+ '                    <div class="bottom-mini-item one-background-color">\n'
+ '                        <div class="mini-label">击杀</div>\n'
+ '                        <div class="mini-value">1.14</div>\n'
+ '                    </div>\n'
+ '                    <div class="bottom-mini-item one-background-color">\n'
+ '                        <div class="mini-label">KD</div>\n'
+ '                        <div class="mini-value">3.13</div>\n'
+ '                    </div>\n'
+ '                </div>\n'
+ '            </div>\n'
+ '        </div>\n'
+ '\n'
+ '        <div class="random-header one-background-color">战舰类型</div>\n'
+ '        <div class="information-body data-battle-type">\n'
+ buildInfoHead()
+ buildInfoCol('战列舰', ['3,897', '65.28%', '#673ab7', '1912', '#00BCD4', '117,015', '#A00DC5', '1.21', '61.1%', '30.93%'])
+ buildInfoCol('巡洋舰', ['3,237', '61.94%', '#673ab7', '1948', '#00BCD4', '86,677', '#A00DC5', '1.05', '60.2%', '34.20%'])
+ buildInfoCol('驱逐舰', ['1,338', '66.14%', '#673ab7', '1964', '#00BCD4', '57,823', '#A00DC5', '1.08', '65.2%', '42.54%'])
+ buildInfoCol('航母', ['1,274', '60.83%', '#673ab7', '1593', '#4CAF50', '105,413', '#A00DC5', '1.22', '79.3%', '0.00%'])
+ buildInfoCol('潜艇', ['84', '42.86%', '#ff9800', '1278', '#FFC107', '36,425', '#FE7903', '0.60', '61.9%', '21.57%'])
+ '        </div>\n'
+ '\n'
+ '        <div class="random-header one-background-color">战斗类型</div>\n'
+ '        <div class="information-body data-battle-type">\n'
+ buildInfoHead()
+ buildInfoCol('单野', ['3,114', '57.13%', '#9c27b0', '1872', '#00BCD4', '93,479', '#A00DC5', '1.12', '61.3%', '34.70%'])
+ buildInfoCol('自行车', ['2,367', '60.08%', '#673ab7', '1837', '#00BCD4', '96,778', '#A00DC5', '1.14', '60.8%', '34.70%'])
+ buildInfoCol('三轮车', ['4,349', '69.99%', '#673ab7', '1897', '#00BCD4', '99,135', '#A00DC5', '1.14', '67.0%', '34.14%'])
+ buildInfoCol('排位', ['425', '57.18%', '#9c27b0', '1667', '#4CAF50', '87,608', '#A00DC5', '0.97', '51.1%', '41.74%'])
+ '        </div>\n'
+ '\n'
+ '        <div class="random-header one-background-color">最高记录</div>\n'
+ '        <div class="frag-data">\n'
+ buildFrag('伤害', '419,610')
+ buildFrag('潜在', '5,711,200')
+ buildFrag('侦查', '339,950')
+ buildFrag('击杀', '8')
+ buildFrag('飞机数', '99')
+ buildFrag('经验', '6,440')
+ '        </div>\n'
+ '\n'
+ '        <div class="chart-box one-background-color">\n'
+ '            <div class="chart-bar"></div>\n'
+ '        </div>\n'
+ '\n'
+ '        <div class="footer">\n'
+ '            <p>频道搜索"战舰世界-yuyuko"即可使用稳定的腾讯官方机器人~</p>\n'
+ '            <p>©github:wows-yuyuko</p>\n'
+ '        </div>\n'
+ '    </div>\n'
+ '</div>\n'
// 回报就绪：iframe 的 load 事件有时对应的是 initial about:blank（那时
// contentDocument 里什么节点都没有），靠这条消息才知道真文档解析完了。
+ '<script>try{parent.postMessage("aep-fixture-ready:' + uid + '","*")}catch(e){}<\/script>\n'
+ '</body>\n'
+ '<script src="' + base + 'echarts.js"><\/script>\n'
+ '<script>\n'
+ 'if (typeof echarts !== "undefined" && document.querySelector(".chart-bar")) {\n'
+ '    var chart = echarts.init(document.querySelector(".chart-bar"));\n'
+ '    chart.setOption({\n'
+ '        animation: false,\n'
+ '        tooltip: {trigger: "axis"},\n'
+ '        legend: {data: ["场次", "胜率"], top: 8, itemWidth: 18, itemHeight: 12,\n'
+ '                 textStyle: {fontSize: 18, color: "#3c3c4c"}},\n'
+ '        grid: {left: 70, right: 80, top: 60, bottom: 30},\n'
+ '        xAxis: {type: "category", axisLabel: {fontSize: 20},\n'
+ '                data: ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "★"]},\n'
+ '        yAxis: [\n'
+ '            {type: "value", name: "场次", nameTextStyle: {fontSize: 16}, axisLabel: {fontSize: 18}},\n'
+ '            {type: "value", name: "胜率(%)", nameTextStyle: {fontSize: 16}, min: 0, max: 100,\n'
+ '             splitLine: {show: false}, axisLabel: {fontSize: 18, formatter: "{value}%"}}\n'
+ '        ],\n'
+ '        series: [\n'
+ '            {name: "场次", type: "bar", barMaxWidth: 56,\n'
+ '             data: [1, 1, 6, 45, 70, 394, 398, 1487, 1989, 5207, 232],\n'
+ '             label: {show: true, position: "top", fontSize: 15, color: "#5a5f6b"},\n'
+ '             itemStyle: {color: "rgba(214, 236, 251, 0.55)", borderColor: "#9FB8FF",\n'
+ '                         borderWidth: 1.5, borderRadius: [6, 6, 0, 0]}},\n'
+ '            {name: "胜率", type: "line", yAxisIndex: 1, smooth: true, symbol: "circle",\n'
+ '             symbolSize: 7, data: [0, 100, 50, 64.44, 62.86, 60.15, 61.81, 62.54, 64.50, 63.88, 62.93],\n'
+ '             itemStyle: {color: "#8D67FF"}, lineStyle: {color: "#8D67FF", width: 3},\n'
+ '             label: {show: true, position: "top", fontSize: 14, color: "#8D67FF"}}\n'
+ '        ]\n'
+ '    });\n'
+ '}\n'
+ '<\/script>\n'
+ '</html>\n';
    }

    function buildInfoHead() {
        var cols = ['类型', '场次', '胜率', 'PR', '场均', '击杀', '存活', '命中'];
        var s = '            <div class="information-col">\n';
        for (var i = 0; i < cols.length; i++) {
            s += '                <div class="information-col-item">' + cols[i] + '</div>\n';
        }
        return s + '            </div>\n';
    }

    function buildInfoCol(name, v) {
        return '            <div class="information-col">\n'
            + '                <div class="information-col-item type-name">' + name + '</div>\n'
            + '                <div class="information-col-item">' + v[0] + '</div>\n'
            + '                <div class="information-col-item" style="color: ' + v[2] + ';">' + v[1] + '</div>\n'
            + '                <div class="information-col-item" style="color: ' + v[4] + ';">' + v[3] + '</div>\n'
            + '                <div class="information-col-item" style="color: ' + v[6] + ';">' + v[5] + '</div>\n'
            + '                <div class="information-col-item">' + v[7] + '</div>\n'
            + '                <div class="information-col-item">' + v[8] + '</div>\n'
            + '                <div class="information-col-item">' + v[9] + '</div>\n'
            + '            </div>\n';
    }

    function buildFrag(k, v) {
        return '            <div class="frag-item one-background-color">\n'
            + '                <div class="frag-key">' + k + '</div>\n'
            + '                <div class="frag-value">' + v + '</div>\n'
            + '            </div>\n';
    }

    /* =====================================================
       HikariUserPreview
       ===================================================== */
    function HikariUserPreview(container, opts) {
        var self = this;
        opts = opts || {};
        this.opts = opts;
        this.el = typeof container === 'string'
            ? document.querySelector(container) : container;
        if (!this.el) throw new Error('HikariUserPreview: 容器不存在');

        this.stageWidth = opts.stageWidth || STAGE_W;
        this.assetBase = normalizeBase(opts.assetBase || DEFAULT_ASSET_BASE);
        this.uid = ++AEP_UID;
        this.ready = false;
        this._pending = null;
        this._lastUserInfo = null;

        // fixture 解析完会 postMessage 回来（比 iframe 的 load 可靠，
        // 首次 load 经常对应 initial about:blank，那时文档里还没有节点）
        this._onMsg = function (e) {
            if (e && e.data === 'aep-fixture-ready:' + self.uid) self._bindFrame();
        };
        global.addEventListener('message', this._onMsg);

        this.build();
        this._bindResize();
    }

    function normalizeBase(b) {
        return b && b.slice(-1) !== '/' ? b + '/' : b;
    }

    HikariUserPreview.prototype.build = function () {
        var self = this;
        this.el.classList.add('aep', 'aep-preview');

        this.viewportEl = el('div', 'aep-viewport');
        this.scalerEl = el('div', 'aep-scaler');

        var frame = document.createElement('iframe');
        frame.className = 'aep-frame';
        frame.setAttribute('scrolling', 'no');
        frame.setAttribute('title', '用户信息预览');
        frame.addEventListener('load', function () { self._bindFrame(); });

        this.frameEl = frame;
        this.scalerEl.appendChild(frame);
        this.viewportEl.appendChild(this.scalerEl);
        this.el.appendChild(this.viewportEl);

        /* 缩放模式切换按钮（浮在预览区右上角）。
           fit / width 两种模式见 fit() 的注释；默认 fit（整页全览）。 */
        this.mode = this.opts.mode === 'width' ? 'width' : 'fit';
        this.modeBtn = el('button', 'aep-fitmode', '整页全览');
        this.modeBtn.type = 'button';
        this.modeBtn.title = '切换缩放方式：整页全览 / 适应宽度';
        this.modeBtn.addEventListener('click', function () { self.toggleMode(); });
        this.el.appendChild(this.modeBtn);
        this._syncModeBtn();

        // srcdoc 必须最后设：先挂监听，避免 load 抢跑
        var fixture = this.opts.fixture || buildFixture(this.assetBase, this.uid);
        frame.srcdoc = fixture;
    };

    HikariUserPreview.prototype._syncModeBtn = function () {
        if (!this.modeBtn) return;
        var fit = this.mode === 'fit';
        this.modeBtn.textContent = fit ? '整页全览' : '适应宽度';
        this.modeBtn.classList.toggle('is-width', !fit);
        this.modeBtn.setAttribute('aria-pressed', String(fit));
        // 提示文字说清「点下去会切到什么」，按钮上写的是当前状态。
        this.modeBtn.title = fit
            ? '当前：整页全览（整页缩进一屏）。点击切到「适应宽度」'
            : '当前：适应宽度（宽度铺满，超高部分滑动）。点击切到「整页全览」';
    };

    /* 切换缩放模式。切换后把滚动位置归零 —— 两种模式的可滚动范围完全不同，
       留着旧的 scrollTop 会停在一个莫名其妙的位置（尤其从 width 切回 fit 时
       fit 根本没得滚，位置会被浏览器夹到 0，不如显式归零来得确定）。 */
    HikariUserPreview.prototype.toggleMode = function () {
        this.mode = this.mode === 'fit' ? 'width' : 'fit';
        this._syncModeBtn();
        if (this.viewportEl) {
            this.viewportEl.scrollTop = 0;
            this.viewportEl.scrollLeft = 0;
        }
        this.fit();
        if (typeof this.onModeChange === 'function') this.onModeChange(this.mode);
    };

    HikariUserPreview.prototype.setMode = function (mode) {
        var next = mode === 'width' ? 'width' : 'fit';
        if (next === this.mode) return;
        this.toggleMode();
    };

    /* 把 iframe 里的真实 v6 文档接过来。
       load 事件和 postMessage 都会走到这里，所以必须幂等 +
       必须能识别「拿到的是 initial about:blank」这种情况（节点还不存在）。 */
    HikariUserPreview.prototype._bindFrame = function () {
        var doc = this.frameEl.contentDocument;
        if (!doc) return;

        var main = doc.querySelector('.main-content');
        if (!main || !doc.querySelector('.page-header')) return;   // 文档还没解析到（或还是 about:blank），等下一次回调

        // 别让 iframe 自己出滚动条（高度由我们按内容设准）
        doc.documentElement.style.overflow = 'hidden';

        this.doc = doc;
        this.dom = {
            main: main,
            header: doc.querySelector('.page-header'),
            masking: doc.querySelector('.masking-header'),
            avatar: doc.querySelector('.avatar-header'),
            infoRow: doc.querySelector('.user-info'),
            tag: doc.querySelector('.aep-tag'),
            name: doc.querySelector('.mirage-text'),
            accountRow: doc.querySelector('.user-account'),
            serverRow: doc.querySelector('.user-server'),
            timeRow: doc.querySelector('.user-sign-time'),
            signRow: doc.querySelector('.user-signature'),
            dynStyle: doc.getElementById('aep-dyn')
        };

        this.ready = true;
        this.fit();
        if (this._pending) {
            var u = this._pending;
            this._pending = null;
            this.render(u);
        } else if (this._lastUserInfo) {
            this.render(this._lastUserInfo);
        }
        if (typeof this.onReady === 'function') this.onReady(this);
    };

    /* ---------- 缩放：两种模式 ----------
       ▍mode = 'fit'（默认，整页全览）
         宽高**同时**塞得下 —— 取「宽度比」和「高度比」里小的那个，
         整页一屏看全，不用滚动。看版式全貌用（背景图铺满没铺满、区块排布对不对）。
         代价：页面很长时字会很小（1500×3700 的页 + 900px 可视高 → 约 24%）。
         这是刻意的取舍 —— 看字请切到 width 模式。

       ▍mode = 'width'（适应宽度）
         老的算法：只按宽度比缩放（availW / 1500），高度溢出就滑动。
         字够大，但看不到整页。

       ▍opt.scale > 0 时是硬指定比例，两种模式都跳过自适应
         （给「固定倍数」这类用法留的口子）。

       ▍高度用 viewportEl.clientHeight 而不是 getBoundingClientRect()：
         前者是内容盒（不含滚动条），跟 scalerEl 里排的东西是同一个参照系。
         「刚好塞下」如果差一条滚动条的量，反而会逼出一条滚动条出来 ——
         整页全览的页面上挂滚动条是自相矛盾的。这里不真去量滚动条厚度
         （跨浏览器读数不稳），而是靠 fit 模式下的二次校验抹掉这点误差。 */
    HikariUserPreview.prototype.fit = function () {
        var availW = this.viewportEl.clientWidth;
        var availH = this.viewportEl.clientHeight;
        if (!availW) return;

        var h = this._measureHeight();          // 原始像素高度（内部会把 iframe 高度定死）

        var k;
        if (this.opts.scale > 0) {
            k = this.opts.scale;
        } else if (this.mode === 'width' || availH <= 0) {
            // width 模式；或容器还没量到高度（首次布局 / 隐藏状态）时按宽度兜底，
            // ResizeObserver 稍后会用真实高度再 fit 一次。
            k = availW / this.stageWidth;
        } else {
            // fit 模式：宽高各算一个「塞得下」的比例，取小的 → 两边都不溢出
            k = Math.min(availW / this.stageWidth, availH / h);
        }

        // 下限兜底：别缩成看不见的一条（1500px 页面 × 0.05 = 75px 宽）。
        k = Math.max(k, 0.05);
        if (!(k > 0) || !isFinite(k)) k = availW / this.stageWidth;

        // fit 模式下缩放后比可视区还高就再压一丁点 —— 抹掉「滚动条厚度」这类
        // 边角误差，保证「不用滚」这个承诺在最后一像素上也成立。
        // （用乘除而不是再调一次 _measureHeight：那个会把 iframe 高度先压到 600px
        //   再量，频繁调用容易闪；这里的 k 是线性的，直接按比例收敛即可。）
        if (this.opts.scale <= 0 && this.mode === 'fit' && availH > 0 && h * k > availH) {
            k = Math.max(k * (availH / (h * k)) - 0.001, 0.05);
        }

        this.scale = k;
        this.frameEl.style.transform = 'scale(' + k + ')';

        // scaler 撑成「缩放后」的真实尺寸 —— 滚动条由它决定。
        // fit 模式下高度正好落在可视区内（不出滚动条）；width 模式下会高出来，
        // 于是纵向滚动条如期出现，正是想要的效果。
        this.scalerEl.style.width = (this.stageWidth * k) + 'px';
        this.scalerEl.style.height = (h * k) + 'px';
    };

    /* iframe 不能 auto 高度：先压到矮值量出内容高，再定死。
       （.main-content 有 min-height:100vh，高度定准后 100vh 就等于内容高，收敛） */
    HikariUserPreview.prototype._measureHeight = function () {
        if (!this.ready) return 1000;
        var doc = this.doc;
        this.frameEl.style.height = '600px';
        var h = Math.max(
            doc.documentElement.scrollHeight || 0,
            doc.body ? doc.body.scrollHeight : 0
        );
        if (h < 600) h = 600;   // 还没布局完时的兜底，别把 iframe 压成一条
        this.frameEl.style.height = h + 'px';
        return h;
    };

    HikariUserPreview.prototype._bindResize = function () {
        var self = this;
        this.fit();
        if (global.ResizeObserver) {
            this._ro = new ResizeObserver(function () { self.fit(); });
            this._ro.observe(this.viewportEl);
        } else {
            this._onWinResize = function () { self.fit(); };
            global.addEventListener('resize', this._onWinResize);
        }
    };

    /* 当前整页尺寸（原始像素，未缩放）—— 大背景图取景框要用 */
    HikariUserPreview.prototype.getStageSize = function () {
        return {
            w: this.stageWidth,
            h: this.ready ? this.dom.main.offsetHeight || this._measureHeight() : 1000
        };
    };

    /* 头部三张图的取景框尺寸（原始像素，取自 v6 样式表） */
    HikariUserPreview.SLOT_FRAME = {
        avatar: { w: AVATAR_BOX, h: AVATAR_BOX },
        banner: { w: PAGE_HEADER_W, h: PAGE_HEADER_H }
    };

    HikariUserPreview.prototype._styleText = function (u) {
        var av = u.avatar || {};
        var poster = av.poster, banner = av.banner, avatar = av.avatar;
        var colorName = av.colorName;
        var css = [];

        var posterOn = !!(poster && num(poster.status, 0) > 0 && poster.data);
        if (posterOn) {
            /* 与 partials/*-v6-macros.html 的 poster 规则同构，改一边记得改另一边：
               背景图挂在 .main-content::before（不能挂 .main-content 本体，
               opacity 会把整页内容一起变淡）。
               两个图层：先列的同尺寸黑色遮罩（alpha = 1 - 不透明度），再列背景图 ——
               遮罩是为了让「完全不透明」时观感与从前一致（从前 url 上套了
               linear-gradient(rgba(0,0,0,.5), ...) 压暗一半），背景图越淡遮罩也越小。
               单值的 background-position / size 会套用到所有图层，写一次即可。 */
            var opacity = posterOpacity(poster);   // dark 是「透明度」，这里换算成 CSS 不透明度
            var maskAlpha = posterMaskAlpha(opacity);
            css.push('.main-content {\n'
                + '    position: relative;\n'
                + '}\n\n'
                + '.main-content::before {\n'
                + '    content: "";\n'
                + '    position: absolute;\n'
                + '    inset: 0;\n'
                + '    z-index: -1;\n'
                + '    opacity: ' + opacity + '%;\n'
                + '    background: linear-gradient(rgba(0, 0, 0, ' + maskAlpha + '), rgba(0, 0, 0, ' + maskAlpha + ')),\n'
                + '                url("' + poster.data + '") no-repeat;\n'
                + '    background-position: ' + cropPos(poster) + ';\n'
                + '    background-size: ' + cropSize(poster, 'cover') + ';\n'
                + '}');
        }

        var colorOn = !!(colorName && num(colorName.status, 0) > 0 && colorName.data);
        if (colorOn) {
            css.push('.mirage-text {\n'
                + '    background: ' + colorName.data + ';\n'
                + '    background-size: 200% 200%;\n'
                + '    color: transparent;\n'
                + '    -webkit-background-clip: text;\n'
                + '    background-clip: text;\n'
                + '}');
        }

        var bannerOn = !!(banner && num(banner.status, 0) > 0 && banner.data);
        css.push('.page-header {\n'
            + (bannerOn ? '    background: url("' + banner.data + '") no-repeat;\n' : '')
            + '    background-position: ' + cropPos(banner) + ';\n'
            + '    background-size: ' + cropSize(banner, '100%') + ';\n'
            + '}');

        var avStatus = avatar ? num(avatar.status, 0) : 0;
        var usingOwn = !!(avStatus > 0 && avatar && avatar.data);
        var dogTag = u.dogTag || '';
        var avatarSrc = (usingOwn ? avatar.data : '') || dogTag;
        css.push('.avatar-header {\n'
            + (avatarSrc ? '    background-image: url("' + avatarSrc + '");\n' : '')
            + '    background-repeat: no-repeat;\n'
            + '    background-position: ' + cropPos(avatar) + ';\n'
            // 回落到 dogTag 时尺寸按默认 100% —— dogTag 是另一张图，套用自定义图的 size 没意义
            + '    background-size: ' + (usingOwn ? cropSize(avatar, '100%') : '100%') + ';\n'
            + '}');

        return css.join('\n\n');
    };

    /* -----------------------------------------------------
       render(userInfo)
       判定口径逐条对应 partials/user-v6-macros.html：
         poster / banner / avatar / colorName / sign 的**背景图**都是 status > 0 才生效
         （status 缺席按 0）；头像在「要不显示图」时回落 dogTag，
         连 dogTag 也没有 -> .no-avatar，信息列左移接管。
         banner.dark == 1       -> .dark-banner，文字转白。
                                  **不判 status** —— 关掉背景图显示不该把深色也取消，
                                  这是两个独立设置（与宏侧同源，改一边记得改另一边）。
         poster.dark 0-100      -> .main-content::before 的 opacity。
                                  dark 是「透明度」（越大越淡），
                                  写进 CSS 的是 100 - dark。
       ----------------------------------------------------- */
    HikariUserPreview.prototype.render = function (userInfo) {
        if (!this.ready) { this._pending = userInfo; return; }

        var u = (userInfo && userInfo.userInfo) ? userInfo.userInfo : (userInfo || {});
        var av = u.avatar || {};
        var d = this.dom;

        var banner = av.banner || null;
        var avatar = av.avatar || null;
        var colorName = av.colorName || null;
        var sign = av.sign || null;
        var dogTag = u.dogTag || '';

        // ---- 三张图 + 彩色昵称：全都靠一份 <style> 输出（与宏同构） ----
        if (d.dynStyle) d.dynStyle.textContent = this._styleText(u);

        // ---- dark-banner：只看 dark == 1，**不判 status** ----
        // 与宏侧 banner_dark 同源：status 管背景图显不显示、dark 管文字黑/白，
        // 是两个独立设置。判 status 会导致「关掉背景图预览」时深色设置一起消失。
        // （banner.dark 是 0/1 深色标记；poster.dark 是 0-100 透明度，
        //   已经在 _styleText 里处理掉了，别在这里再读它）
        var bannerOn = !!(banner && num(banner.status, 0) > 0 && banner.data);
        var isDark = !!(banner && num(banner.dark, 0) === 1);
        d.header.classList.toggle('dark-banner', isDark);

        // ---- 头像：status > 0 用自定义图，否则回落 dogTag ----
        var avatarOn = !!(avatar && num(avatar.status, 0) > 0 && avatar.data);
        var avatarSrc = (avatarOn ? avatar.data : '') || dogTag;
        d.masking.classList.toggle('no-avatar', !avatarSrc);

        // ---- 彩色昵称 ----
        var colorOn = !!(colorName && num(colorName.status, 0) > 0 && colorName.data);
        d.infoRow.classList.toggle('no-color-name', !colorOn);

        // ---- 名字 / 军团标签 ----
        var clan = u.clanInfo || null;
        var tag = (clan && clan.tag) || '';
        var tagColor = (clan && clan.color) || '#b3b3b3';
        d.tag.textContent = tag ? '[' + tag + ']' : '';
        d.tag.style.display = tag ? '' : 'none';
        d.tag.style.color = isDark ? '#ffffff' : tagColor;
        d.name.textContent = u.userName || '';

        // ---- 账号 / 服务器 / 注册时间 ----
        var uid = (u.accountId !== undefined && u.accountId !== null) ? u.accountId : 'N/A';
        d.accountRow.textContent = 'Account Id: ' + uid;
        d.serverRow.textContent = '所属服务器: ' + serverCn(u);
        d.timeRow.textContent = '注册时间: ' + fmtTime(u.accountCreateTime);

        // ---- 个性签名：有签名时「服务器 / Account Id」并成一行 ----
        var signOn = !!(sign && num(sign.status, 0) > 0 && sign.data);
        d.signRow.style.display = signOn ? '' : 'none';
        d.signRow.textContent = signOn ? sign.data : '';
        if (signOn) {
            d.accountRow.style.display = 'none';
            d.serverRow.textContent = '服务器: ' + serverCn(u) + ' / Account Id: ' + uid;
            d.serverRow.style.display = '';
        } else {
            d.accountRow.style.display = '';
            d.serverRow.textContent = '所属服务器: ' + serverCn(u);
            d.serverRow.style.display = '';
        }

        this._lastUserInfo = u;
        this.fit();
    };

    HikariUserPreview.prototype.getUserInfo = function () {
        return this._lastUserInfo;
    };

    HikariUserPreview.prototype.destroy = function () {
        if (this._ro) this._ro.disconnect();
        if (this._onMsg) global.removeEventListener('message', this._onMsg);
        if (this._onWinResize) global.removeEventListener('resize', this._onWinResize);
        if (this.el) this.el.innerHTML = '';
        this.ready = false;
    };

    /* =====================================================
       HikariImageCropper —— 基于 Cropper.js 的取景裁剪器
       -----------------------------------------------------
       交互对齐参考实现 https://wows.mgaia.top/cutting
       （那个站用的就是 Cropper.js v1 + Vue + Element Plus）：
         · 图片完整显示在取景容器里（contain），框外依然可见
         · 一个可拖动、可拉伸的裁剪框浮在图片上，8 个手柄随便拽
         · 滚轮缩放图片 / 拖动换位置，viewMode: 1 保证框永远在图片内
       裁剪框的宽高比 = 模板盒子的比例（头像 1:1、小背景 1400:300、
       大背景 1500:整页高），所以框里框到的内容天然就是要塞进那个盒子的东西。

       对外仍然吐同一套 crop：
         x / y   百分比，直接给模板的 background-position
         size    百分比字符串，直接给模板的 background-size
         scale   相对「初始框」的倍数（1 = 框最大 = 模板默认，5 = 放到 5 倍）

       容器尺寸是 0（弹窗还没打开）时不会初始化 Cropper —— 要等 relayout()。
       ===================================================== */
    function HikariImageCropper(container, opts) {
        opts = opts || {};
        this.opts = opts;
        this.el = typeof container === 'string'
            ? document.querySelector(container) : container;
        if (!this.el) throw new Error('HikariImageCropper: 容器不存在');

        this.frame = opts.frame || { w: 250, h: 250 };
        this.aspect = this.frame.w / this.frame.h;
        /* freeAspect: 裁剪框不锁宽高比，手柄随便拉。
           适合模板里本来就「不在乎图片比例」的槽位：
             · 小背景图 background-size: 100%  -> 宽度撑满，高度多余部分被裁
             · 大背景图 background-size: cover -> 等比放大到盖住整个盒子
           头像那种固定方框（250×250）就必须锁 1:1，否则画面会变形。 */
        this.freeAspect = !!opts.freeAspect;
        this.stageHeight = opts.maxHeight || 300;
        this.label = opts.label || '';
        this.minScale = 1;                    // 1 = 框最大（就是模板默认状态）
        this.maxScale = opts.maxZoom || 5;

        this.src = '';
        this.cropper = null;
        this.ready = false;
        this.scale = 1;
        this._sizeDefault = null;             // 初始框对应的 size(%)，scale 的基准
        // 最近一次「框」的宽高比。自由比例槽位用 setData 定位时得沿用当前框比例，
        // 不能从 getData 现取 —— 用户改成 dragMode:'move'（拖图不拖框）之后，
        // 拖图会触发 crop 事件而框本身没变，但 getData 的时序不完全可控。
        this._boxRatio = this.aspect;
        this._pendingPos = null;
        this._resolveImage = null;

        this._build();
    }

    HikariImageCropper.prototype._build = function () {
        var self = this;
        this.el.classList.add('aep', 'aep-crop');

        this.canvas = el('div', 'aep-crop-canvas');
        // 舞台高度走 CSS 变量 —— 这样 CSS 里还能用 max-height 按视口把它压低
        this.canvas.style.setProperty('--aep-stage-h', this.stageHeight + 'px');
        this.img = el('img', 'aep-crop-img');
        this.img.alt = '';
        this.canvas.appendChild(this.img);

        this.meta = el('div', 'aep-crop-meta');

        this.el.appendChild(this.canvas);
        this.el.appendChild(this.meta);

        // actions: false 时不画自带的「居中 / 下载」—— 交给外面的弹窗工具栏画
        if (opts_actions(this.opts)) {
            this.actions = el('div', 'aep-crop-actions');
            this.btnReset = el('button', 'aep-btn', '居中');
            this.btnReset.type = 'button';
            this.btnExport = el('button', 'aep-btn', '下载裁剪图');
            this.btnExport.type = 'button';
            this.actions.appendChild(this.btnReset);
            this.actions.appendChild(this.btnExport);
            this.el.appendChild(this.actions);
            this.btnReset.addEventListener('click', function () { self.reset(); });
            this.btnExport.addEventListener('click', function () { self.download(); });
        }

        this._renderMeta();
    };

    function opts_actions(opts) {
        return !opts || opts.actions !== false;
    }

    HikariImageCropper.prototype._cropOpts = function () {
        var self = this;
        return {
            // 锁比例时用模板盒子比例；freeAspect 时用 NaN（Cropper 的「自由」）
            aspectRatio: this.freeAspect ? NaN : this.aspect,
            viewMode: 1,                // 框不能跑出图片（就是「不能超过图片边界」）
            /* 拖动 = 搬图片（crop box 留在原地）。
               之前是 'crop' + movable:false，也就是拖的是那个框 ——
               数学上「动框」和「动图」等价，但手感完全不对：用户看着图片纹丝不动，
               以为根本拖不了。参考站（wows.mgaia.top/cutting）也是拖图。
               配合 viewMode:1（图片始终盖满容器，没有可拖的边界）；
               要单独改框的位置直接拽框内部即可 —— viewMode:1 下 Cropper 对
               cropBox 的 mousedown 有判断，这时不会误触发图片拖动。 */
            dragMode: 'move',
            autoCropArea: 1,            // 初始框尽量大
            movable: true,              // 图片可以拖（滚轮缩放之外的第二只手）
            zoomable: true,             // 滚轮缩放图片
            zoomOnWheel: true,
            scalable: false,
            rotatable: false,
            background: false,          // 不用 Cropper 自带的棋盘底，用我们自己的
            modal: true,                // 框外半透明遮罩
            highlight: false,
            guides: true,
            center: true,
            responsive: true,
            /* 必须 false。开着的话 Cropper 会给 img 加上 crossorigin="anonymous"，
               而没开放跨域的图源（q.qlogo.cn 这类）会**直接加载失败、整张图都不显示**。
               关掉之后图一定显示得出来；代价是导出裁剪图时 canvas 可能被污染，
               那种情况 toDataURL 会抛错，我们返回 null 并提示换本地上传的图。 */
            checkCrossOrigin: false,
            /* ready / crop 这类回调**必须写在 option 里**：
               Cropper 内部是 `addListener(element, 'ready', options.ready, {once:true})`
               + `element.dispatchEvent(new CustomEvent('ready'))`，
               用的是原生 DOM 事件；实例上**没有** `.on()` / `.off()` 方法。
               （v1.6.2 的 prototype 只有 getData/setData/replace/… 这些动作方法。） */
            ready: function () { self._onReady(); },
            crop: function () { self._emit(); }
        };
    };

    HikariImageCropper.prototype._onReady = function () {
        if (this.ready) return;                 // ready 可能被事件 + 兜底各触发一次
        this.ready = true;
        this._sizeDefault = this._measureDefault();
        if (this._pendingPos) {
            this._targetPos = this._pendingPos;
            this._pendingPos = null;
        }
        if (!this._targetPos) this._targetPos = { x: 50, y: 50, scale: 1 };
        this._writePos();
        this._emit();
        if (this._resolveImage) { this._resolveImage(true); this._resolveImage = null; }

        // Cropper 稳定下来还要一两帧，按同一个目标再写一次：
        // 否则容器矮的时候初始位置会被它的边界收敛压到边上（实测 50% 变 100%）。
        // 用户这期间要是拖了框，_emit 已经把 _targetPos 更新过，不会跳回去。
        var self = this;
        global.setTimeout(function () {
            if (!self.ready) return;
            self._writePos();
            self._emit();
        }, 150);
    };

    /* 当前框对应的 size(%) = 图宽 / 框宽。
       锁比例且框最大时算出来正好是模板默认值：
       头像 / 小背景 = 100%，大背景 = cover 等价的百分比（如 115.57%）。 */
    HikariImageCropper.prototype._measureSize = function () {
        if (!this.cropper) return 100;
        var d = this.cropper.getData(true);
        var id = this.cropper.getImageData();
        var nw = (id && id.naturalWidth) || 0;
        if (!nw || !d.width) return 100;
        return nw / d.width * 100;
    };

    /* 初始框对应的 size(%)，也就是 scale = 1 的基准。
       锁比例时它就是 autoCropArea=1 的那个框（框尽量大）；
       自由比例时要手动算成「刚好盖住模板盒子」的框 —— 否则初始框会是整图，
       遇到 cover 的槽位（大背景图）一上来就上下露白。 */
    HikariImageCropper.prototype._measureDefault = function () {
        var nw = 0, nh = 0;
        if (this.ready && this.cropper) {
            var id = this.cropper.getImageData();
            nw = id.naturalWidth;
            nh = id.naturalHeight;
        }
        if (!this.freeAspect || !nw || !nh) return this._measureSize();
        var w = Math.min(nw, nh * this.frame.w / this.frame.h);
        return nw / w * 100;
    };

    /* 容器有尺寸之后才建 Cropper（弹窗打开时调）。
       img 必须先有 src —— Cropper 构造时就会去读它。 */
    HikariImageCropper.prototype._ensureCropper = function () {
        if (this.cropper || !this.src) return;
        if (typeof global.Cropper !== 'function') {
            throw new Error('HikariImageCropper: 没找到 Cropper，确认页面引了 cropper.min.js');
        }
        var self = this;
        this.img.src = this.src;
        this.cropper = new global.Cropper(this.img, this._cropOpts());
        // 图片已经在缓存里时 cropper.buildImage 会走同步分支，
        // ready 在构造函数返回前就发完了 —— 用实例上的 ready 标记补一次
        if (this.cropper.ready) self._onReady();
    };

    HikariImageCropper.prototype.setImage = function (src) {
        var self = this;
        src = src || '';
        this.src = src;

        if (!src) {
            if (this.cropper) { this.cropper.destroy(); this.cropper = null; }
            this.ready = false;
            this._sizeDefault = null;
            this._renderMeta();
            return Promise.resolve(false);
        }
        // 还没进过弹窗（容器没尺寸）就先记着；容器已经有尺寸的话顺手补建一次
        // —— 弹窗可能在数据回来之前就打开了，那时 src 还是空的。
        // 返回 false 不影响调用方：紧接着的 setPosition 会落到 _pendingPos，
        // 等 Cropper 的 ready 事件再把位置还原回去。
        if (!this.cropper) {
            this.relayout();
            this._renderMeta();
            return Promise.resolve(false);
        }
        return new Promise(function (resolve) {
            self._resolveImage = resolve;
            self.cropper.replace(src);
            global.setTimeout(function () {
                if (self._resolveImage) { self._resolveImage(!!self.ready); self._resolveImage = null; }
            }, 8000);
        });
    };

    /* 弹窗打开 / 容器尺寸变化时调。
       Cropper.js **没有** resize() 方法，而我们是「容器量到尺寸之后才 new」，
       所以这里保证它被建起来就够了；窗口缩放它自己用 responsive 处理。 */
    HikariImageCropper.prototype.relayout = function () {
        if (!this.el.clientWidth) return;     // 还在隐藏状态，等下一次
        this._ensureCropper();
        this._renderMeta();
    };

    HikariImageCropper.prototype._emit = function () {
        if (!this.ready) { this._renderMeta(); return; }
        // 记住框的比例（自由比例槽位 _writePos 要用）。
        // 这个必须在 getPosition 之前记：getPosition 只读、不改 Cropper。
        var d = this.cropper.getData(true);
        if (d.width > 0 && d.height > 0) this._boxRatio = d.width / d.height;
        this._applyEmit(this.getPosition());
        // 拖到边界时拖不动了，但 mouseup 之后 Cropper 还会把图片位置收敛一次
        // （拖过头的那一截被规整回合法范围，crop 事件在这之后不一定再发）。
        // 不补这一下，预览会停在「手指离开时」的位置，跟画布差一截 —— 必须重读。
        if (d.movable) this._pinEmit();
    };

    /* 松手那一帧再兜一次：位置校正完把预览拉回和画布一致 */
    HikariImageCropper.prototype._pinEmit = function () {
        if (!this.ready || !this.cropper) return;
        var self = this;
        [0, 120].forEach(function (ms) {
            global.setTimeout(function () {
                if (!self.ready || !self.cropper) return;
                self._applyEmit(self.getPosition(), true);
            }, ms);
        });
    };

    /* 落一次 onChange + 元信息。
       force 是给 _pinEmit 用的：位置校正那一下数值可能刚好没变，
       但预览必须重绘（它在拖拽中间收到过旧值）。 */
    HikariImageCropper.prototype._applyEmit = function (p, force) {
        if (!force && this._lastEmit
            && this._lastEmit.x === p.x && this._lastEmit.y === p.y
            && this._lastEmit.size === p.size) return;
        this._lastEmit = { x: p.x, y: p.y, size: p.size };
        this.scale = p.scale;
        // 跟住当前实际位置：用户在弹窗里拖完图，这里要把目标同步过来，
        // 免得 _onReady 里那个"延迟校正"把他刚拖的结果又拽回去
        this._targetPos = { x: p.x, y: p.y, scale: p.scale };
        this._renderMeta(p);
        if (typeof this.onChange === 'function') this.onChange(p, this);
    };

    /* 框在**原图坐标系**里的位置 -> 模板要的百分比 */
    HikariImageCropper.prototype.getPosition = function () {
        if (!this.ready || !this.cropper) {
            return { x: 50, y: 50, scale: 1, size: '100%' };
        }
        var d = this.cropper.getData(true);
        var id = this.cropper.getImageData();
        var nw = id.naturalWidth, nh = id.naturalHeight;
        var size = d.width > 0 ? (nw / d.width * 100) : 100;
        /* 溢出不足 1px 就当作「没有可移动空间」，一律报 50% 居中。
           不加这道判断的话，浮点误差会造出一个几乎为零的除数把位置算飞
           —— 实测：框宽正好等于「刚好盖住盒子」时，垂直溢出只有 0.085px，
           结果 y 被算成 20 万，夹取后变成 100%（贴底）而不是居中。 */
        var xOver = nw - d.width;
        var x = xOver > 1 ? (d.x / xOver * 100) : 50;
        var y;
        if (this.freeAspect) {
            /* 自由比例时垂直方向要另算：模板那边 background-size 只给宽度，
               高度是图自己按原始比例撑出来的，所以"溢出"不是 图高−框高，
               而是「图片按 size 渲染后的高 − 盒子高」：
                   渲染高 = 盒宽 × nh / 框宽
                   溢出   = 盒宽 × nh / 框宽 − 盒高
                   Q      = (框顶 × 盒宽/框宽) / 溢出 × 100
                          = 框顶 × 盒宽 / (nh × 盒宽 − 盒高 × 框宽) × 100
               框宽高比和盒子一致时会自动退化成原来的 框顶/(图高−框高) ✓ */
            var Wb = this.frame.w, Hb = this.frame.h;
            var over = nh * Wb - Hb * d.width;          // 注意：这是「溢出 × 框宽」
            var overPx = d.width > 0 ? over / d.width : 0;
            y = overPx > 1 ? (d.y * Wb / over * 100) : 50;
        } else {
            var yOver = nh - d.height;
            y = yOver > 1 ? (d.y / yOver * 100) : 50;
        }
        var scale = this._sizeDefault ? (size / this._sizeDefault) : 1;
        return {
            x: Math.round(clamp(x, 0, 100) * 100) / 100,
            y: Math.round(clamp(y, 0, 100) * 100) / 100,
            scale: Math.round(clamp(scale, 0.001, 1000) * 1000) / 1000,
            size: (Math.round(size * 100) / 100) + '%'
        };
    };

    /* 把「想要的位置」记在 _targetPos 上，再落到 Cropper。
       之所以要分开：Cropper 在 ready 之后还会做一次尺寸/边界收敛，
       紧接着的 setData 有时会被它压回去（实测容器矮的时候，本来设成 50% 居中
       的初始位置会变成 100% 贴边）。所以 _onReady 里会隔两帧按同一个目标重写一次。 */
    HikariImageCropper.prototype._applyPos = function (x, y, scale) {
        // 自由比例下 Cropper 会按当前框比例把 setData 的 height 一改，
        // 框比例就悄悄变了 —— 把用户实际的框比例先记下来，
        // 否则紧接着的 setData 会按旧比例写回去，看着像「点一下框就变形」。
        if (this.ready && this.cropper) {
            var cur = this.cropper.getData(true);
            if (cur.width > 0 && cur.height > 0) this._boxRatio = cur.width / cur.height;
        }
        this._targetPos = {
            x: typeof x === 'number' ? x : 50,
            y: typeof y === 'number' ? y : 50,
            scale: typeof scale === 'number' ? scale : 1
        };
        if (!this.ready || !this.cropper) {
            this._pendingPos = { x: this._targetPos.x, y: this._targetPos.y, scale: this._targetPos.scale };
            return this;
        }
        this._writePos();
        return this;
    };

    HikariImageCropper.prototype._writePos = function () {
        var t = this._targetPos;
        if (!t || !this.ready || !this.cropper) return;
        var id = this.cropper.getImageData();
        var nw = id.naturalWidth, nh = id.naturalHeight;
        var s = clamp(t.scale, this.minScale, this.maxScale);
        var w = nw * 100 / ((this._sizeDefault || 100) * s);
        var h;
        if (this.freeAspect) {
            // 自由比例：宽度按 size 反算，高度沿用**框**的宽高比
            //（初始框就是「刚好盖住盒子」的那个，所以一上来不会露白）
            h = w / (this._boxRatio || nw / nh || 1);
        } else {
            h = w / this.aspect;
        }
        if (h > nh) {
            var k = w / h;       // 先留住当前宽高比，别被下面的赋值带跑
            h = nh;
            w = h * (this.freeAspect ? k : this.aspect);
        }
        this.cropper.setData({
            x: clamp(t.x, 0, 100) / 100 * Math.max(0, nw - w),
            y: clamp(t.y, 0, 100) / 100 * Math.max(0, nh - h),
            width: w,
            height: h
        });
        this.scale = s;
    };

    HikariImageCropper.prototype.setPosition = function (x, y, scale) {
        return this._applyPos(
            typeof x === 'number' ? x : 50,
            typeof y === 'number' ? y : 50,
            scale
        );
    };

    HikariImageCropper.prototype.getScale = function () { return this.scale; };

    HikariImageCropper.prototype.setScale = function (s) {
        var p = this.getPosition();
        return this._applyPos(p.x, p.y, s);
    };

    /* 只把框挪回图片正中（缩放不动） */
    HikariImageCropper.prototype.center = function () {
        var p = this.getPosition();
        return this._applyPos(50, 50, p.scale);
    };

    /* 完全恢复默认：图片缩放 + 框大小/位置一起复位。
       注意 Cropper 里这是**两套独立的变换**：
         · 图片（canvas）的缩放/位移 —— 滚轮或拖图改的是它
         · 裁剪框（crop box）的大小/位置 —— 拖框/拉手柄改的是它
       _writePos 只动裁剪框，管不到图片缩放，所以这里必须先调
       cropper.reset() 把 canvas 也还原，否则滚轮放大过的图看着"没重置"。 */
    HikariImageCropper.prototype.reset = function () {
        if (this.ready && this.cropper && typeof this.cropper.reset === 'function') {
            this.cropper.reset();
        }
        return this._applyPos(50, 50, 1);
    };

    /* 容器尺寸变了（比如弹窗切全屏）时调。
       Cropper.js **没有** resize()，它的 responsive 也只认 window resize，
       容器自己变尺寸不会自动重算 —— 只能拆了重建；重建前先把当前位置记下来，
       再交给 _targetPos，ready 后会照着还原。 */
    HikariImageCropper.prototype.onResize = function () {
        if (!this.cropper) return this;
        var p = this.getPosition();
        this.cropper.destroy();
        this.cropper = null;
        this.ready = false;
        this._sizeDefault = null;
        this._targetPos = { x: p.x, y: p.y, scale: p.scale };
        this._ensureCropper();
        return this;
    };

    HikariImageCropper.prototype.setFrame = function (frame) {
        var ar = frame.w / frame.h;
        var changed = Math.abs(ar - this.aspect) >= 1e-6;
        this.frame = { w: frame.w, h: frame.h };
        this.aspect = ar;
        // 只有锁比例时才需要跟着改框、重算基准。自由比例下框是用户自己拉的；
        // 而且 _sizeDefault 不能每次重算 —— 预览的页面高度一浮动（poster 的
        // frame.h 就是这么来的），scale 会跟着抖，滑块看着就乱跳。
        if (!this.freeAspect && changed && this.cropper) {
            this.cropper.setAspectRatio(ar);
            this._sizeDefault = this._measureSize();
        }
        return this;
    };

    HikariImageCropper.prototype._renderMeta = function (p) {
        var parts = [];
        parts.push('取景框比例 <b>' + this.frame.w + '×' + this.frame.h + '</b>');
        if (!this.ready || !this.cropper) {
            parts.push(this.src ? '打开弹窗后初始化' : '未选择图片');
            this.meta.innerHTML = wrapSpans(parts);
            return;
        }
        p = p || this.getPosition();
        var id = this.cropper.getImageData();
        var d = this.cropper.getData(true);
        parts.push('原图 <b>' + id.naturalWidth + '×' + id.naturalHeight + '</b>');
        parts.push('裁剪区域 <b>' + Math.round(d.width) + '×' + Math.round(d.height) + '</b>');
        parts.push('缩放 <b>' + p.scale.toFixed(2) + '×</b>');
        parts.push('background-position <b>' + p.x.toFixed(1) + '% ' + p.y.toFixed(1) + '%</b>');
        parts.push('background-size <b>' + p.size + '</b>');
        this.meta.innerHTML = wrapSpans(parts);
    };

    function wrapSpans(list) {
        return list.map(function (s) { return '<span>' + s + '</span>'; }).join('');
    }

    /* 导出裁剪结果（原图分辨率；getCroppedCanvas 会自动处理缩放） */
    HikariImageCropper.prototype.toDataURL = function (type, quality) {
        if (!this.ready || !this.cropper) return null;
        var d = this.cropper.getData(true);
        var canvas;
        try {
            canvas = this.cropper.getCroppedCanvas({
                width: Math.max(1, Math.round(d.width)),
                height: Math.max(1, Math.round(d.height)),
                imageSmoothingEnabled: true,
                imageSmoothingQuality: 'high'
            });
        } catch (e) {
            return null;
        }
        if (!canvas) return null;
        try {
            return canvas.toDataURL(type || 'image/png', quality);
        } catch (e) {
            return null;   // 跨域污染
        }
    };

    HikariImageCropper.prototype.download = function (name) {
        if (!this.ready) {
            global.alert('图片还没加载好，无法导出。');
            return;
        }
        var data = this.toDataURL('image/png');
        if (!data) {
            global.alert('导出失败：这张图可能没开放跨域（浏览器不允许把它画进 canvas）。\n'
                + '换成本地上传的图片再试。');
            return;
        }
        var a = document.createElement('a');
        a.href = data;
        a.download = (name || this.label || 'crop') + '.png';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    };

    HikariImageCropper.prototype.destroy = function () {
        if (this.cropper) { this.cropper.destroy(); this.cropper = null; }
        this.ready = false;
        this.el.innerHTML = '';
    };

    /* =====================================================
       让模板也吃 crop 位置（可选）
       宏 user-v6-macros.html 里三处写的都是 background-position: center，
       想跟随设置页存下来的 crop，把 center 换成：
           {{ (slot.crop.x if slot.crop else 50) }}% {{ (slot.crop.y if slot.crop else 50) }}%
       本组件渲染预览时就是这么做的（见 _styleText）。
       ===================================================== */

    /* =====================================================
       彩色昵称用的「颜色值 <-> 配置」工具
       -----------------------------------------------------
       colorName.data 直接写进模板的 background（再配 background-clip: text），
       实际只会是两种形态：
           纯色        #rrggbb
           线性渐变    linear-gradient(45deg, #a 0%, #b 100%)
                       （老数据里还可能是 -webkit-linear-gradient(...)，一样认）
       解析成配置 -> 面板里编辑 -> 再拼回 CSS，往返必须稳定：
       解析出来的色标位置是 null 时，拼回去按等距插值补上。
       ===================================================== */
    function splitTop(s) {
        var out = [], depth = 0, cur = '';
        for (var i = 0; i < s.length; i++) {
            var c = s.charAt(i);
            if (c === '(') depth++;
            else if (c === ')') depth--;
            if (c === ',' && depth === 0) { out.push(cur); cur = ''; }
            else cur += c;
        }
        out.push(cur);
        return out;
    }

    var HikariColorUtil = {
        /* 按顶层逗号切分（忽略 rgba(1,2,3) 里的逗号） */
        splitTop: splitTop,

        defaultCfg: function () {
            return { type: 'solid', color: '#e53935', angle: 45, stops: [] };
        },

        /* 认不出来（例如 url(...) 图片）返回 null，调用方应保留原值 */
        parse: function (v) {
            v = String(v == null ? '' : v).trim();
            var m = /^(?:-webkit-)?(?:repeating-)?linear-gradient\((.*)\)$/i.exec(v);
            if (m) {
                var parts = splitTop(m[1]).map(function (s) { return s.trim(); })
                    .filter(function (s) { return !!s; });
                var angle = 45, stops = [];
                var head = (parts[0] || '').toLowerCase();
                if (/^-?[\d.]+deg$/.test(head)) {
                    angle = parseFloat(head);
                    parts.shift();
                } else if (/^to\s/.test(head)) {
                    angle = 180;   // "to right" 之类，近似成 180
                    parts.shift();
                }
                parts.forEach(function (p) {
                    var mm = /^(.+?)\s+(-?[\d.]+)%$/.exec(p);
                    if (mm) stops.push({ color: mm[1].trim(), pos: parseFloat(mm[2]) });
                    else stops.push({ color: p, pos: null });
                });
                if (stops.length >= 2) {
                    return { type: 'gradient', angle: angle, stops: stops, color: '#e53935' };
                }
            }
            if (/^#[0-9a-f]{3}$/i.test(v) || /^#[0-9a-f]{6}$/i.test(v)) {
                return { type: 'solid', color: v, angle: 45, stops: [] };
            }
            return null;
        },

        build: function (cfg) {
            cfg = cfg || {};
            if (cfg.type === 'solid') return cfg.color || '#000000';
            var stops = cfg.stops || [];
            var n = stops.length;
            var parts = stops.map(function (s, i) {
                var pos = (s.pos === null || s.pos === undefined || isNaN(s.pos))
                    ? (n > 1 ? i / (n - 1) * 100 : 0)
                    : Number(s.pos);
                return s.color + ' ' + (Math.round(pos * 10) / 10) + '%';
            });
            return 'linear-gradient(' + (cfg.angle == null ? 45 : cfg.angle) + 'deg, '
                + parts.join(', ') + ')';
        }
    };

    global.HikariColorUtil = HikariColorUtil;

    global.HikariUserPreview = HikariUserPreview;
    global.HikariImageCropper = HikariImageCropper;

    global.HikariBuild = HIKARI_BUILD;
}(typeof window !== 'undefined' ? window : this));
