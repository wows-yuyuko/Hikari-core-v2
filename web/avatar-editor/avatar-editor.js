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
         ▍**两张页面都预览**（顶栏下拉框切换，见 TEMPLATES）：
            · info  用户信息页 wws-info-v6.html  —— 长页（≈2600px）
            · ship  单船页     wws-ship-v6.html  —— 短页（大背景图纵向对齐在这里才看得出来）
           两张共用**同一份头部**（info_header 宏），所以头像 / 小背景 / 大背景 /
           彩色昵称 / 签名 / 卡片旋钮切来切去都照样生效。
         ▍两份数据各管一块，别搞混：
            · **头像设置**（avatar 那几个槽位 / card）来自
              /public/wows/account/search/db/{id} 的 data，走 .render(userInfo)
              —— 就是设置页正在改的那份，改一下预览立刻变。
            · **战力数据**（PR 条 / 场次 / 胜率 / 图表…）按**当前模板**分开存：
              info 用 /public/wows/account/user/info2 的 data（.setInfoData），
              ship 用 /public/wows/account/ship/info 的 data（.setShipData），
              都是只读的真实数据，不给就用内置演示快照（DEMO_INFO / DEMO_SHIP）。
         .render(userInfo)   —— 吃接口 /public/wows/account/search/db/{id}
                                返回的 data（顶层就是 userInfo 字段）；
                                传 {userInfo:{...}} 包装形式也认
         .setTemplate('info'|'ship') 换预览哪张页面（重建文档）
         .setInfoData(data)  —— 换一份 info2 的真实战力数据（重建信息区块）；
                                传 null 回到演示快照
         .getInfoData()      -> 当前那份 info2 数据（没设过是 null）
         .setShipData(data)  —— 换一份单船数据（同上）；null 回演示快照
         .getShipData()      -> 当前那份单船数据（没设过是 null）
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
   ▍poster.dark  = 0-100 大背景图透明度（0 = 不透明 / 100 = 全透明，越大越淡）
   ▍大背景图的**纵向取景位置固定贴顶**（background-position 纵向恒 0%）——
     不可配、也没有对应字段了（原先有个 poster.align，2026-09-19 起连同面板旋钮一起撤掉，
     宏侧同样写死 0，见 partials/*-v6-macros.html 的 poster_pos_y 注释）。
     只有页高 < 2250px 的短页才看得出这条：长页按高贴合、纵向整幅铺满，
     贴顶与居中渲染完全相同；短页按宽贴合、纵向被裁，固定贴顶才能保证各页取景一致。
   ▍另有一个**不是槽位**的全局配置（没有 status / data / crop，也不是图片）：
       avatar.card = { dark: 0-100, blur: 0-200 }
                   毛玻璃「元素块」的两个旋钮 —— 卡片底色透明度 / 模糊强度，
                   以 CSS 变量 --card-alpha / --card-blur 下发到 .main-content，
                   与宏同构、**只在有海报时生效**。见 cardVarsCss()。
   status 判断口径**完全照抄** partials/user-v6-macros.html，见 render() 注释。
   crop 是设置页附加的字段，模板侧**不读它**（宏里 background-position 的横向恒为
   center）—— 所以「拖动平移」目前只在预览里生效。想让模板也吃这个位置，
   把宏里的 `center` 换成 crop.x 即可（默认 50 与 center 等价，改不改都不影响老数据）。
   （纵向不可用 crop.y 表达：预览的取景框 = 实时页高，cover 之下纵向溢出≈0，
     getPosition() 一律报 50 —— 所以它当年是另开的 align 字段，现在干脆固定贴顶。）
   ========================================================= */
(function (global) {
    'use strict';

    /* 这套组件的版本标记 —— 改了 index.html / avatar-editor.js / avatar-editor.css
       里任何一处，就把时间顺手改一下（只要让页面能看出「刷新真的生效了」）。
       页面顶栏会显示它：改完代码刷新后时间没变，说明浏览器还在用缓存里的旧文件
       （Ctrl+F5 强制刷新即可）。
       （不走 ?v= 查询串是因为 file:// 下查询串会被当成文件名，直接加载失败。） */
    var HIKARI_BUILD = '2026-09-19 21:26';

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

    /* 只要 crop 的横向那半（大背景图的纵向恒为贴顶，见 POSTER_POS_Y_TOP）。 */
    function cropPosX(slot) {
        var c = slot && slot.crop;
        var x = c && typeof c.x === 'number' ? c.x : 50;
        return clamp(x, 0, 100);
    }

    /* 大背景图的**纵向取景位置：固定贴顶**（0%）—— 与 partials/*-v6-macros.html 的
       poster_pos_y 严格同构（改一边记得改另一边）。
       ▍**不再读 poster.align**：原先这是一个可调字段（0-100 或 'top'|'center'|'bottom'，
         缺省居中），2026-09-19 起产品决定固定顶部，面板旋钮也撤了 —— 老数据里
         存着的对齐值一律忽略。要改回可调得同时动四处：两个宏 + 这里 + index.html 面板。
       ▍为什么固定顶部：这个值只在页面比 2250px 矮时才看得出来。
         分界点 = 图高 4096 × 容器宽 1500 / 图宽 2731 = 2250px：
           页高 ≥ 2250 → 按高贴合、纵向正好铺满 → **贴顶与居中渲染完全相同**；
           页高 < 2250 → 按宽贴合、纵向被裁 → 只有贴顶能保证各页取景一致。
       ▍为什么不走 crop.y：预览的 poster 取景框 = **实时页高**，而 cover 之下纵向溢出≈0，
         getPosition() 里「溢出不足 1px 就当没有可移动空间、一律报 50%」那条判断会把它
         钉死在 50 —— 纵向本来就无法用拖动表达。（这条是当年另开 align 的原因，
         也是现在"干脆写死"的前提。） */
    var POSTER_POS_Y_TOP = 0;

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

    /* 毛玻璃「元素块」（卡片）的两个全局旋钮 —— 与 partials/*-v6-macros.html 的
       card 段**严格同构**（改一边记得改另一边）：
         card.dark  0-100  卡片底色透明度，**与 poster.dark 同向**：越大越淡，
                           0 = 完全不透明 = 缺省（即当前观感）
         card.blur  0-200  毛玻璃模糊强度百分比：100 = 缺省（当前观感），
                           0 = 完全不模糊，200 = 两倍
       下发方式与模板一致：写成 .main-content 上的 --card-alpha / --card-blur，
       由 main-v6.css / avatar-v6.css 里各条 background / backdrop-filter 去乘。
       ▍**只在有海报时才下发**（调用点在 _styleText 的 posterOn 分支里）：
         没海报时真实渲染会由 main-v6.js 把卡片整套换成实色，旋钮在那时没有意义；
         预览要是照样下发，就成了「预览有效果、成品没效果」。
       ▍缺省口径必须和宏的 `| int(缺省)` 对齐：字段缺席 / null / 空串 / 非整数串
         都回缺省，float 按**截断**（Jinja 的 int(12.7) = 12，不是四舍五入）。
         这就是下面不用现成的 num() 的原因 —— 那个走 parseInt，
         对 '12.5' 会取到 12，而 Jinja 的 int('12.5') 认不了、会回缺省。 */
    function cardIntOr(v, dflt) {
        if (v === undefined || v === null || v === '') return dflt;
        if (typeof v === 'string' && !/^\s*[+-]?\d+\s*$/.test(v)) return dflt;
        var n = Number(v);
        if (!isFinite(n)) return dflt;
        return n < 0 ? Math.ceil(n) : Math.floor(n);
    }

    /* 「两位小数的倍数」字符串，与宏的
       `(pct // 100) | int ~ '.' ~ '%02d' | format(pct % 100)` 逐字对齐。
       ▍这里不能用 toFixed：宏的整数部分走的是整数除法（截断），
         两边一旦不同，预览的底色浓淡就和成品差一档。 */
    function ratioStr(pct) {
        var whole = Math.floor(pct / 100);
        var frac = String(Math.floor(pct) % 100);
        if (frac.length < 2) frac = '0' + frac;
        return whole + '.' + frac;
    }

    /* 输出 .main-content 里那两行变量声明（含缩进与换行，直接拼进规则块）。
       ▍永远输出合法数字：var() 拿到空串 / 畸形值会让整条 background /
         backdrop-filter 在「计算值阶段」失效（底色直接透明、模糊直接没了），
         而且不报错 —— 与上面 poster 的坑同源。 */
    function cardVarsCss(slot) {
        var dark = clamp(cardIntOr(slot && slot.dark, 0), 0, 100);
        var blur = clamp(cardIntOr(slot && slot.blur, 100), 0, 200);
        return '    --card-alpha: ' + ratioStr(100 - dark) + ';\n'
             + '    --card-blur: ' + ratioStr(blur) + ';\n';
    }

    /* =====================================================
       预览骨架：**真实 v6 渲染产物的结构**
       取自 tests/data/wows-yuyuko/temp_image/me.html（wws-info-v6 渲染结果），
       真类名、真内容块、真 ECharts 配置，只把 userInfo 那几个节点留空壳，
       由 render() 填。CSS 走 assetBase 指向的真实 v6 样式表
       —— 所以预览长什么样，机器人渲染出来就长什么样。

       ▍信息区块（PR 条 / 最新战斗时间 / 核心数据 / 战舰类型 / 战斗类型 /
       最高记录 / 等级图表）是**按数据生成的**：下面每个 builder 都逐条照抄
       Template/wws-info-v6.html 的取数与排版口径（颜色缺省、存活率的三元表达式、
       空级别在胜率线上写 null……），改模板那几段就回来改这里 —— 与宏
       「改一边记得改另一边」是同一条规矩。
         数据来源 = /public/wows/account/user/info2 的 data，见 setInfoData()；
         没有数据时用演示快照 DEMO_INFO，版面永远有东西看。
       ===================================================== */

    /* 演示快照：**结构与 info2 的 data 完全一致**（只裁掉渲染用不到的字段），
       所以它和真实数据走同一套 builder，不存在「两条排版路径」。
       取自亚服 2022515210 的一次真实响应。
       ▍lastBattleTime / prInfo / userInfo.prStatus 都参与渲染：
         少一个就会让「最后战斗时间」变 N/A、或整条 PR 消失 —— 改这份数据时留神。 */
    var DEMO_INFO = {
        lastBattleTime: 1789739954,
        prInfo: {value: 1868, name: '非常好', color: '#00BCD4'},
        userInfo: {prStatus: 0},
        battleTypeInfo: {
            PVP: {battle: 9853, prInfo: {value: 1873, color: '#00BCD4'}, shipInfo: {battleInfo: {battle: 9853, survived: 6276}, avgInfo: {win: 63.53, winsData: {color: '#673ab7'}, damage: 96790, damageData: {color: '#A00DC5'}, frags: 1.14, kd: 3.13, xp: 2295, planesKilled: 6}, hitRatioInfo: {ratioMain: 34.46, ratioTpd: 5.93}, maxInfo: {maxDamageDealt: {value: 419610}, maxTotalAgro: {value: 5711200}, maxScoutingDamage: {value: 339950}, maxFrags: {value: 8}, maxPlanesKilled: {value: 99}, maxXp: {value: 6440}}}},
            PVP_SOLO: {battle: 3115, prInfo: {value: 1872, color: '#00BCD4'}, shipInfo: {battleInfo: {battle: 3115, survived: 1910}, avgInfo: {win: 57.11, winsData: {color: '#9c27b0'}, damage: 93494, damageData: {color: '#A00DC5'}, frags: 1.12, kd: 2.91, xp: 2169, planesKilled: 5}, hitRatioInfo: {ratioMain: 34.7, ratioTpd: 6.08}}},
            PVP_DIV2: {battle: 2368, prInfo: {value: 1837, color: '#00BCD4'}, shipInfo: {battleInfo: {battle: 2368, survived: 1438}, avgInfo: {win: 60.05, winsData: {color: '#673ab7'}, damage: 96781, damageData: {color: '#A00DC5'}, frags: 1.14, kd: 2.9, xp: 2281, planesKilled: 6}, hitRatioInfo: {ratioMain: 34.71, ratioTpd: 6.09}}},
            PVP_DIV3: {battle: 4370, prInfo: {value: 1896, color: '#00BCD4'}, shipInfo: {battleInfo: {battle: 4370, survived: 2928}, avgInfo: {win: 70, winsData: {color: '#673ab7'}, damage: 99145, damageData: {color: '#A00DC5'}, frags: 1.14, kd: 3.46, xp: 2393, planesKilled: 6}, hitRatioInfo: {ratioMain: 34.15, ratioTpd: 5.76}}},
            RANK_SOLO: {battle: 425, prInfo: {value: 1667, color: '#4CAF50'}, shipInfo: {battleInfo: {battle: 425, survived: 217}, avgInfo: {win: 57.18, winsData: {color: '#9c27b0'}, damage: 87608, damageData: {color: '#A00DC5'}, frags: 0.97, kd: 1.99, xp: 2194, planesKilled: 4}, hitRatioInfo: {ratioMain: 41.74, ratioTpd: 7.28}}}
        },
        shipTypeInfo: {
            Battleship: {PVP: {battle: 3904, prInfo: {value: 1912, color: '#00BCD4'}, shipInfo: {battleInfo: {battle: 3904, survived: 2384}, avgInfo: {win: 65.29, winsData: {color: '#673ab7'}, damage: 117033, damageData: {color: '#A00DC5'}, frags: 1.21, kd: 3.1, xp: 2397, planesKilled: 5}, hitRatioInfo: {ratioMain: 30.93, ratioTpd: 4.59}}}},
            Cruiser: {PVP: {battle: 3248, prInfo: {value: 1949, color: '#00BCD4'}, shipInfo: {battleInfo: {battle: 3248, survived: 1954}, avgInfo: {win: 61.88, winsData: {color: '#673ab7'}, damage: 86788, damageData: {color: '#A00DC5'}, frags: 1.05, kd: 2.64, xp: 2237, planesKilled: 7}, hitRatioInfo: {ratioMain: 34.22, ratioTpd: 2.85}}}},
            Destroyer: {PVP: {battle: 1343, prInfo: {value: 1959, color: '#00BCD4'}, shipInfo: {battleInfo: {battle: 1343, survived: 876}, avgInfo: {win: 66.27, winsData: {color: '#673ab7'}, damage: 57731, damageData: {color: '#A00DC5'}, frags: 1.08, kd: 3.11, xp: 2277, planesKilled: 5}, hitRatioInfo: {ratioMain: 42.55, ratioTpd: 6.13}}}},
            AirCarrier: {PVP: {battle: 1274, prInfo: {value: 1593, color: '#4CAF50'}, shipInfo: {battleInfo: {battle: 1274, survived: 1010}, avgInfo: {win: 60.83, winsData: {color: '#673ab7'}, damage: 105413, damageData: {color: '#A00DC5'}, frags: 1.22, kd: 5.91, xp: 2186, planesKilled: 5}, hitRatioInfo: {ratioMain: 0, ratioTpd: 0}}}},
            Submarine: {PVP: {battle: 84, prInfo: {value: 1279, color: '#FFC107'}, shipInfo: {battleInfo: {battle: 84, survived: 52}, avgInfo: {win: 42.86, winsData: {color: '#ff9800'}, damage: 36425, damageData: {color: '#FE7903'}, frags: 0.6, kd: 1.56, xp: 1740, planesKilled: 0}, hitRatioInfo: {ratioMain: 18.18, ratioTpd: 21.57}}}}
        },
        levelInfo: {
            '1': {PVP: {shipInfo: {battleInfo: {battle: 1}, avgInfo: {win: 0}}}},
            '2': {PVP: {shipInfo: {battleInfo: {battle: 1}, avgInfo: {win: 100}}}},
            '3': {PVP: {shipInfo: {battleInfo: {battle: 6}, avgInfo: {win: 50}}}},
            '4': {PVP: {shipInfo: {battleInfo: {battle: 45}, avgInfo: {win: 64.44}}}},
            '5': {PVP: {shipInfo: {battleInfo: {battle: 70}, avgInfo: {win: 62.86}}}},
            '6': {PVP: {shipInfo: {battleInfo: {battle: 394}, avgInfo: {win: 60.15}}}},
            '7': {PVP: {shipInfo: {battleInfo: {battle: 399}, avgInfo: {win: 61.65}}}},
            '8': {PVP: {shipInfo: {battleInfo: {battle: 1487}, avgInfo: {win: 62.54}}}},
            '9': {PVP: {shipInfo: {battleInfo: {battle: 1989}, avgInfo: {win: 64.5}}}},
            '10': {PVP: {shipInfo: {battleInfo: {battle: 5229}, avgInfo: {win: 63.89}}}},
            '11': {PVP: {shipInfo: {battleInfo: {battle: 232}, avgInfo: {win: 62.93}}}}
        }
    };

    /* 单船页的演示快照 —— 结构与 /public/wows/account/ship/info 的 data 一致
       （只裁掉渲染用不到的字段：dwpData / rank / shipInfo 的那几张别的尺寸图…）。
       取自亚服 2022515210 的真实响应，shipId 4276041424（大和）。
       ▍与 DEMO_INFO 是**两份不同的数据**：单船页的战斗块结构比用户页少一层
         （typeInfo[bt].battleInfo 直接挂着，没有 shipInfo），所以两边各用各的取数器。
       ▍typeInfo[bt].battle 是**布尔标记**（打没打过），场次在 battleInfo.battleInfo.battle
         —— 模板里 `{% if data['typeInfo']['PVP']['battle'] %}` 判的就是这个布尔值，
         别拿它当数字用。
       ▍PVP 那几个 branch 各带自己的 prInfo / battleInfo；只有 PVP 有 maxInfo 与
         originalServer（最高记录 / 服务器数据两块只读 PVP）。 */
    var DEMO_SHIP = {
        shipInfo: {nameCn:'大和',levelStr:'X',shipTypeImage:'https://v3-api.wows.shinoaki.com/nahida-static/wows/Battleship-ShipType-image.png',countryImage:'https://v3-api.wows.shinoaki.com/nahida-static/wows/Japan-Nation-image.png',imgSmall:'https://v3-api.wows.shinoaki.com/nahida-static/ship_cache/asia-4276041424-small.png'},
        userInfo: {server:'asia',serverCn:'亚服',accountId:2022515210,userName:'Nahida_official',accountCreateTime:1549278766,dogTag:'https://v3-api.wows.shinoaki.com/nahida-static/root/2022515210.png',prStatus:0,clanInfo:{tag:'YU_RI',color:'#b3b3b3'}},
        typeInfo: {
            PVP: {battle:true,prInfo:{value:1740,name:'很好',color:'#4CAF50',details:{originalServer:{damage:84826.7,wins:48.77,frags:0.65}}},battleInfo:{battleInfo:{battle:187,survived:111},avgInfo:{damage:115953,damageData:{color:'#A00DC5'},win:54.55,winsData:{color:'#00bcd4'},kd:2.09,frags:0.85,xp:2410,planesKilled:3},hitRatioInfo:{ratioMain:29.14,ratioTpd:0.0},lastBattleTime:1789610923,maxInfo:{maxDamageDealt:{value:337943},maxTotalAgro:{value:3868318},maxScoutingDamage:{value:78635},maxFrags:{value:4},maxPlanesKilled:{value:22},maxXp:{value:5465}}}},
            PVP_SOLO: {battle:true,prInfo:{value:1619,name:'很好',color:'#4CAF50'},battleInfo:{battleInfo:{battle:76,survived:50},avgInfo:{damage:105429,damageData:{color:'#A00DC5'},win:52.63,winsData:{color:'#00bcd4'},kd:2.73,frags:0.93,xp:2358,planesKilled:3},hitRatioInfo:{ratioMain:27.49,ratioTpd:0.0}}},
            PVP_DIV2: {battle:true,prInfo:{value:1520,name:'好',color:'#8BC34A'},battleInfo:{battleInfo:{battle:50,survived:24},avgInfo:{damage:111956,damageData:{color:'#A00DC5'},win:46.0,winsData:{color:'#8bc34a'},kd:1.35,frags:0.7,xp:2226,planesKilled:3},hitRatioInfo:{ratioMain:29.44,ratioTpd:0.0}}},
            PVP_DIV3: {battle:true,prInfo:{value:2071,name:'非常好',color:'#00BCD4'},battleInfo:{battleInfo:{battle:61,survived:37},avgInfo:{damage:132342,damageData:{color:'#A00DC5'},win:63.93,winsData:{color:'#673ab7'},kd:2.21,frags:0.87,xp:2626,planesKilled:4},hitRatioInfo:{ratioMain:30.73,ratioTpd:0.0}}},
            RANK_SOLO: {battle:false,prInfo:{value:0,name:'暂无数据',color:'#828282'},battleInfo:{battleInfo:{battle:0,survived:0},avgInfo:{damage:0,damageData:{color:'#FE7903'},win:0.0,winsData:{color:'#f44336'},kd:0.0,frags:0.0,xp:0,planesKilled:0},hitRatioInfo:{ratioMain:0.0,ratioTpd:0.0}}}
        }
    };

    /* 模板里写死的两张表的行（顺序、中文名、命中率取哪一列都照抄 wws-info-v6.html）：
       潜艇的命中率取 ratioTpd（鱼雷），其余取 ratioMain。 */
    var SHIP_TYPE_ROWS = [
        ['Battleship', '战列舰', 'ratioMain'],
        ['Cruiser', '巡洋舰', 'ratioMain'],
        ['Destroyer', '驱逐舰', 'ratioMain'],
        ['AirCarrier', '航母', 'ratioMain'],
        ['Submarine', '潜艇', 'ratioTpd']
    ];
    var BATTLE_TYPE_ROWS = [
        ['PVP_SOLO', '单野'], ['PVP_DIV2', '自行车'], ['PVP_DIV3', '三轮车'], ['RANK_SOLO', '排位']
    ];

    /* ---------- 数值格式化：与 Jinja 的 '{:,}' / '%.2f' / '%.1f' 同构 ----------
       模板那边写的是 '{:,}'.format(x) 和 '%.2f' | format(x)，这里必须给出**逐字
       相同**的字符串，否则「预览即成品」这个前提就破了。
       ▍缺字段 / null / 非数字一律当 0：Jinja 遇到缺字段会直接报错，而预览是版式
         工具 —— 不能因为接口少一个字段就整页白屏，那样反而看不出问题在哪。 */
    function infoNum(v) {
        var n = Number(v);
        return isFinite(n) ? n : 0;
    }

    /* '{:,}' —— 千分位。整数照抄；值是浮点时只给整数部分加分隔符
       （别让它退化成科学计数法）。 */
    function fmtInt(v) {
        var n = infoNum(v);
        var parts = String(Math.abs(n)).split('.');
        var head = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        return (n < 0 ? '-' : '') + head + (parts[1] ? '.' + parts[1] : '');
    }

    /* '%.2f' / '%.1f' */
    function fmtFix(v, digits) {
        return infoNum(v).toFixed(digits);
    }

    /* 存活率 = 存活场次 / 总场次 × 100（0 场取 0）—— 就是模板里的三元表达式。 */
    function surviveRatio(b) {
        return b.battle > 0 ? b.survived / b.battle * 100 : 0;
    }

    /* battleTypeInfo[bt] / shipTypeInfo[st]['PVP'] / levelInfo[lv]['PVP'] 是同一个
       「战斗块」结构，这里统一取成渲染要用的那几个数（颜色的缺省值照抄模板的兜底）。 */
    function battleOf(tb) {
        var si = (tb && tb.shipInfo) || {};
        var bi = si.battleInfo || {};
        var av = si.avgInfo || {};
        var pr = (tb && tb.prInfo) || {};
        return {
            battle: infoNum(bi.battle),
            survived: infoNum(bi.survived),
            win: infoNum(av.win),
            winColor: (av.winsData || {}).color || '#673ab7',
            damage: infoNum(av.damage),
            damageColor: (av.damageData || {}).color || '#A00DC5',
            frags: infoNum(av.frags),
            kd: infoNum(av.kd),
            xp: infoNum(av.xp),
            planesKilled: infoNum(av.planesKilled),
            hitMain: infoNum((si.hitRatioInfo || {}).ratioMain),
            hitTpd: infoNum((si.hitRatioInfo || {}).ratioTpd),
            pr: infoNum(pr.value),
            prColor: pr.color || '#828282'
        };
    }

    /* PR 条 —— 与 common-v6-macros.html 的 info_pr() 同构。 */
    function buildPr(pr) {
        return '        <div class="pr" style="background: ' + (pr.color || '#828282') + ';">\n'
+ '            <div class="svg-waves">\n'
+ '                <svg viewBox="0 0 500 200" preserveAspectRatio="none">\n'
+ '                    <path class="wave-path" d="M0,100 C150,200 350,0 500,100 L500,200 L0,200 Z"></path>\n'
+ '                </svg>\n'
+ '            </div>\n'
+ '            <span class="pr-number">' + infoNum(pr.value) + '\n'
+ '                <span class="pr-text">' + (pr.name || '') + '</span></span>\n'
+ '        </div>\n';
    }

    /* 核心数据的一个格子：大数字 + 两个小项。color 为空 = 不写 style
       （模板里「场次」那格本来就没有颜色）。 */
    function buildStatItem(label, value, color, minis) {
        return '            <div class="overview-change-item">\n'
+ '                <div class="item-top one-background-color">\n'
+ '                    <div class="stat-label">' + label + '</div>\n'
+ '                    <div class="stat-value"' + (color ? ' style="color: ' + color + ';"' : '') + '>' + value + '</div>\n'
+ '                </div>\n'
+ '                <div class="item-bottom">\n'
+ minis.map(function (m) {
        return '                    <div class="bottom-mini-item one-background-color">\n'
+ '                        <div class="mini-label">' + m[0] + '</div>\n'
+ '                        <div class="mini-value">' + m[1] + '</div>\n'
+ '                    </div>\n';
    }).join('')
+ '                </div>\n'
+ '            </div>\n';
    }

    function buildOverview(main) {
        return '        <div class="overview-change">\n'
+ buildStatItem('场次', fmtInt(main.battle), '',
        [['加成经验', fmtInt(main.xp)], ['命中率', fmtFix(main.hitMain, 2) + '%']])
+ buildStatItem('胜率', fmtFix(main.win, 2) + '%', main.winColor,
        [['存活率', fmtFix(surviveRatio(main), 1) + '%'], ['击落', fmtFix(main.planesKilled, 2)]])
+ buildStatItem('场均', fmtInt(main.damage), main.damageColor,
        [['击杀', fmtFix(main.frags, 2)], ['KD', fmtFix(main.kd, 2)]])
+ '        </div>\n';
    }

    /* 表头：PR 列随 userInfo.prStatus 出现 / 消失（模板的 show_pr）。 */
    function buildInfoHead(showPr) {
        var cols = ['类型', '场次', '胜率'];
        if (showPr) cols.push('PR');
        cols = cols.concat(['场均', '击杀', '存活', '命中']);
        var s = '            <div class="information-col">\n';
        for (var i = 0; i < cols.length; i++) {
            s += '                <div class="information-col-item">' + cols[i] + '</div>\n';
        }
        return s + '            </div>\n';
    }

    /* 表里的一行（两张表共用）。ratioKey 决定命中率取哪一列。 */
    function buildInfoRow(name, b, ratioKey, showPr) {
        return '            <div class="information-col">\n'
+ '                <div class="information-col-item type-name">' + name + '</div>\n'
+ '                <div class="information-col-item">' + fmtInt(b.battle) + '</div>\n'
+ '                <div class="information-col-item" style="color: ' + b.winColor + ';">' + fmtFix(b.win, 2) + '%</div>\n'
+ (showPr ? '                <div class="information-col-item" style="color: ' + b.prColor + ';">' + b.pr + '</div>\n' : '')
+ '                <div class="information-col-item" style="color: ' + b.damageColor + ';">' + fmtInt(b.damage) + '</div>\n'
+ '                <div class="information-col-item">' + fmtFix(b.frags, 2) + '</div>\n'
+ '                <div class="information-col-item">' + fmtFix(surviveRatio(b), 1) + '%</div>\n'
+ '                <div class="information-col-item">' + fmtFix(ratioKey === 'ratioTpd' ? b.hitTpd : b.hitMain, 2) + '%</div>\n'
+ '            </div>\n';
    }

    /* 最高记录的一格 —— 与模板的 .frag-item 同构。 */
    function buildFrag(k, v) {
        return '            <div class="frag-item one-background-color">\n'
+ '                <div class="frag-key">' + k + '</div>\n'
+ '                <div class="frag-value">' + v + '</div>\n'
+ '            </div>\n';
    }

    /* 等级图表的两条数据：1..11 级的场次与胜率。
       ▍没有场次的级别在**胜率线上写 null**（ECharts 会把线断开）—— 模板里
         {% if ... > 0 %}...{% else %}null{% endif %} 就是干这个的。别写成 0，
         否则曲线上会凭空多出一个「胜率 0%」的坑。 */
    function levelChartData(d) {
        var battles = [], wins = [];
        for (var lv = 1; lv <= 11; lv++) {
            var b = battleOf(((d.levelInfo || {})[String(lv)] || {}).PVP);
            battles.push(String(b.battle));
            wins.push(b.battle > 0 ? fmtFix(b.win, 2) : 'null');
        }
        return { battles: battles.join(', '), wins: wins.join(', ') };
    }

    /* -----------------------------------------------------
       fixture 的公共外壳 / 公共部件 —— 用户页与单船页共用
       ▍外壳：真 v6 样式表 + 空的 <style id="aep-dyn">（头像设置的动态 CSS 由
         _styleText() 灌进去）+ 回报就绪的 postMessage + 尾部脚本。
       ▍**故意不引 main-v6.js**：它一加载就按「当时有没有海报」注入一套实色主题，
         而预览的海报是后面 render() 才挂上去的 —— 那套兜底一旦注入就会永久盖住海报，
         「有海报」的预览直接失真。代价是「无海报」时卡片偏玻璃（已知偏差），
         两个模板保持一致。
       ▍回报就绪那段不能省：iframe 的 load 事件有时对应 initial about:blank，
         那时文档里一个节点都没有（_bindFrame 会自己判出来并跳过）。 */
    function fixtureShell(base, uid, bodyHtml, tailHtml) {
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
+ bodyHtml
+ '\n'
+ footerBlock()
+ '    </div>\n'
+ '</div>\n'
+ '<script>try{parent.postMessage("aep-fixture-ready:' + uid + '","*")}catch(e){}<\/script>\n'
+ '</body>\n'
+ (tailHtml || '')
+ '</html>\n';
    }

    /* 头部 —— partials/user-v6-macros.html 的 info_header() 的**空壳版**：
       类名与层级照抄宏的输出，tag / 名字 / 账号 / 服务器 / 注册时间 / 签名一律留空，
       由 HikariUserPreview.render() 按「头像设置」填。
       ▍用户页与单船页调的是**同一个** info_header 宏，所以这只有一份、两边共用
         （改宏记得回来改这里）—— 这也是「切模板后头像设置照样生效」的原因。 */
    function headerBlock() {
        return '        <div class="page-header">\n'
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
+ '        </div>\n';
    }

    /* 页脚 —— common-v6-macros.html 的 footer_box()，两个模板共用。 */
    function footerBlock() {
        return '        <div class="footer">\n'
+ '            <p>频道搜索"战舰世界-yuyuko"即可使用稳定的腾讯官方机器人~</p>\n'
+ '            <p>©github:wows-yuyuko</p>\n'
+ '        </div>\n';
    }

    function buildFixture(base, uid, info) {
        var d = info || DEMO_INFO;                 // 没有真实数据 → 演示快照
        var u = d.userInfo || {};
        var pr = d.prInfo || {};
        var bt = d.battleTypeInfo || {};
        /* 口径照抄模板开头两行：
             show_pr = userInfo.prStatus != 1        → PR 条与 PR 列一起开关
             main    = 打过仗的 PVP，没打过就退到排位 */
        var showPr = infoNum(u.prStatus) !== 1;
        var main = battleOf(bt.PVP);
        if (main.battle <= 0) main = battleOf(bt.RANK_SOLO);

        /* 两张表都只画「有场次」的行 —— 模板里是 {% if info['battle'] %} 过滤。
           零场次的行画出来只会是一排 0，不是成品的样子。 */
        var shipRows = '';
        SHIP_TYPE_ROWS.forEach(function (t) {
            var b = battleOf(((d.shipTypeInfo || {})[t[0]] || {}).PVP);
            if (b.battle > 0) shipRows += buildInfoRow(t[1], b, t[2], showPr);
        });
        var battleRows = '';
        BATTLE_TYPE_ROWS.forEach(function (t) {
            var b = battleOf(bt[t[0]]);
            if (b.battle > 0) battleRows += buildInfoRow(t[1], b, 'ratioMain', showPr);
        });

        var max = ((bt.PVP || {}).shipInfo || {}).maxInfo || {};
        function maxVal(key) { return fmtInt((max[key] || {}).value); }

        var chart = levelChartData(d);
        var last = infoNum(d.lastBattleTime);
        var lastText = last > 0 ? fmtTime(last) : 'N/A';

        return fixtureShell(base, uid,
            headerBlock()
+ '\n'
+ (showPr && infoNum(pr.value) > 0 ? buildPr(pr) + '\n' : '')
+ '        <div class="recnet-time">\n'
+ '            <span class="time-item">最后战斗时间：' + lastText + '</span>\n'
+ '        </div>\n'
+ '\n'
+ buildOverview(main)
+ '\n'
+ '        <div class="random-header one-background-color">战舰类型</div>\n'
+ '        <div class="information-body data-battle-type">\n'
+ buildInfoHead(showPr)
+ shipRows
+ '        </div>\n'
+ '\n'
+ '        <div class="random-header one-background-color">战斗类型</div>\n'
+ '        <div class="information-body data-battle-type">\n'
+ buildInfoHead(showPr)
+ battleRows
+ '        </div>\n'
+ '\n'
+ '        <div class="random-header one-background-color">最高记录</div>\n'
+ '        <div class="frag-data">\n'
+ buildFrag('伤害', maxVal('maxDamageDealt'))
+ buildFrag('潜在', maxVal('maxTotalAgro'))
+ buildFrag('侦查', maxVal('maxScoutingDamage'))
+ buildFrag('击杀', maxVal('maxFrags'))
+ buildFrag('飞机数', maxVal('maxPlanesKilled'))
+ buildFrag('经验', maxVal('maxXp'))
+ '        </div>\n'
+ '\n'
+ '        <div class="chart-box one-background-color">\n'
+ '            <div class="chart-bar"></div>\n'
+ '        </div>\n',
            '<script src="' + base + 'echarts.js"><\/script>\n'
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
+ '             data: [' + chart.battles + '],\n'
+ '             label: {show: true, position: "top", fontSize: 15, color: "#5a5f6b"},\n'
+ '             itemStyle: {color: "rgba(214, 236, 251, 0.55)", borderColor: "#9FB8FF",\n'
+ '                         borderWidth: 1.5, borderRadius: [6, 6, 0, 0]}},\n'
+ '            {name: "胜率", type: "line", yAxisIndex: 1, smooth: true, symbol: "circle",\n'
+ '             symbolSize: 7, data: [' + chart.wins + '],\n'
+ '             itemStyle: {color: "#8D67FF"}, lineStyle: {color: "#8D67FF", width: 3},\n'
+ '             label: {show: true, position: "top", fontSize: 14, color: "#8D67FF"}}\n'
+ '        ]\n'
+ '    });\n'
+ '}\n'
+ '<\/script>\n');
    }

    /* =====================================================
       单船页预览骨架：**真实 wws-ship-v6 渲染产物的结构**
       逐块照抄 Template/wws-ship-v6.html + partials/common-v6-macros.html 的
       ship_header / info_pr / footer_box；头部件走**共用的** headerBlock()
       （两边调的是同一个 info_header 宏），所以头像设置那套补丁不必分叉。
       改模板那几段就回来改这里 —— 与用户页信息区块是同一条规矩。

       ▍与用户页的三处结构性差异（都是模板本身的差异，不是简化）：
         1. 战斗块少一层：单船是 typeInfo[bt].battleInfo.xxx，用户页是
            typeInfo[bt].shipInfo.battleInfo.xxx —— 取数器分开，别混用；
         2. 核心数据那排的类名不同（left/mid/right-item + overview-count/win/avgdmg），
            用户页用的是 overview-change-item + stat-label/stat-value；
         3. 单船页的场次 / 加成经验 / PR / 最高记录 / 服务器数据都是**裸输出**
            （模板里没有 {:} 千分位），用户页那边才带千分位 —— 所以用 fmtRaw 而非 fmtInt。
       ===================================================== */

    /* 单船页「战斗类型」表的四行 —— 顺序 / 中文名照抄 wws-ship-v6.html。 */
    var SHIP_BATTLE_ROWS = [
        ['PVP_SOLO', '单野'], ['PVP_DIV2', '自行车'], ['PVP_DIV3', '三轮车'], ['RANK_SOLO', '排位']
    ];

    /* 裸输出：模板里就是 `{{ x }}`，**不套 '{:,}'**。
       与 fmtInt 分开是有意的 —— 单船页的场次 / 加成经验 / PR / 最高记录
       在成品里都不带千分位，套上去就是「预览 ≠ 成品」。
       （这些字段在接口里都是整数，所以 String() 与 Python 印出来的逐字一致。） */
    function fmtRaw(v) { return String(infoNum(v)); }

    /* 单船页的战斗块取数器。结构与用户页不同（少一层 shipInfo）：
           typeInfo[bt] = {battle: 布尔, prInfo, battleInfo: {battleInfo, avgInfo,
                           hitRatioInfo, maxInfo, lastBattleTime}}
       ▍bt.battle 是「打没打过」的布尔标记，场次在 battleInfo.battleInfo.battle。 */
    function shipBattleOf(tb) {
        var bi = (tb && tb.battleInfo) || {};
        var b = bi.battleInfo || {};
        var av = bi.avgInfo || {};
        var h = bi.hitRatioInfo || {};
        var pr = (tb && tb.prInfo) || {};
        return {
            battle: infoNum(b.battle),
            survived: infoNum(b.survived),
            win: infoNum(av.win),
            winColor: (av.winsData || {}).color || '#673ab7',
            damage: infoNum(av.damage),
            damageColor: (av.damageData || {}).color || '#A00DC5',
            frags: infoNum(av.frags),
            kd: infoNum(av.kd),
            xp: infoNum(av.xp),
            planesKilled: infoNum(av.planesKilled),
            hitMain: infoNum(h.ratioMain),
            hitTpd: infoNum(h.ratioTpd),
            pr: infoNum(pr.value),
            prColor: pr.color || '#828282',
            prName: pr.name || ''
        };
    }

    /* 顶部船名条 —— common-v6-macros.html 的 ship_header()。 */
    function shipHeaderBlock(ship) {
        ship = ship || {};
        var icons = [[ship.countryImage], [ship.shipTypeImage]].map(function (t) {
            return '                <span style="background: url(\'' + (t[0] || '')
                + '\') no-repeat; background-size: contain; background-position: center; padding: 34px;"></span>\n';
        }).join('');
        return '        <div class="ship-header">\n'
+ '            <div class="ship-title-pill one-background-color">\n'
+ icons
+ '                <span>' + (ship.levelStr || '') + '</span>\n'
+ '                <img class="ship-box" src="' + (ship.imgSmall || '') + '" style="width: 120px; height: 100%;">\n'
+ '                <span class="ship-title-name">' + (ship.nameCn || '') + '</span>\n'
+ '            </div>\n'
+ '        </div>\n';
    }

    /* 核心数据方块的底排小项。三个方块用两套盒子类名（见模板）：
       左/中是 change-avgdmg-box + change-win-box，右边换成 overview-kd-box +
       overview-hit-box，后面再挂 bottom-mini-item-left / -right。 */
    function shipMiniBox(boxCls, isLeft, label, value) {
        return '                    <div class="' + boxCls + ' bottom-mini-item-'
            + (isLeft ? 'left' : 'right') + ' one-background-color">\n'
+ '                        <div class="mini-item-top">' + label + '</div>\n'
+ '                        <div class="mini-item-bottom">' + value + '</div>\n'
+ '                    </div>\n';
    }

    /* 核心数据那一排：场次 / 胜率 / 场均。
       ▍PVP 与 RANK_SOLO 两个分支在模板里是**各写一遍**、排版逐字相同的，
         所以这里只实现一份，由调用方决定喂哪块数据（取数见 buildShipFixture）。 */
    function shipOverview(b) {
        return '        <div class="overview-change">\n'
+ '            <div class="overview-change-item left-item">\n'
+ '                <div class="left-item-top item-top one-background-color">\n'
+ '                    <div class="overview-count-title item-top-top">场次</div>\n'
+ '                    <div class="overview-count item-top-bottom">' + fmtRaw(b.battle) + '</div>\n'
+ '                </div>\n'
+ '                <div class="left-item-bottom item-bottom">\n'
+ shipMiniBox('change-avgdmg-box', true, '加成经验', fmtRaw(b.xp))
+ shipMiniBox('change-win-box', false, '命中率', fmtFix(b.hitMain, 2) + '%')
+ '                </div>\n'
+ '            </div>\n'
+ '            <div class="overview-change-item mid-item">\n'
+ '                <div class="mid-item-top item-top one-background-color">\n'
+ '                    <div class="overview-win-title item-top-top">胜率</div>\n'
+ '                    <div class="overview-win item-top-bottom" style="color: ' + b.winColor + ';">'
+ fmtFix(b.win, 2) + '%</div>\n'
+ '                </div>\n'
+ '                <div class="mid-item-bottom item-bottom">\n'
+ shipMiniBox('change-avgdmg-box', true, '存活率', fmtFix(surviveRatio(b), 1) + '%')
+ shipMiniBox('change-win-box', false, '击落', fmtFix(b.planesKilled, 2))
+ '                </div>\n'
+ '            </div>\n'
+ '            <div class="overview-change-item right-item">\n'
+ '                <div class="right-item-top item-top one-background-color">\n'
+ '                    <div class="overview-avgdmg-title item-top-top">场均</div>\n'
+ '                    <div class="overview-avgdmg item-top-bottom" style="color: ' + b.damageColor + ';">'
+ fmtInt(b.damage) + '</div>\n'
+ '                </div>\n'
+ '                <div class="right-item-bottom item-bottom">\n'
+ shipMiniBox('overview-kd-box', true, '击杀', fmtFix(b.frags, 2))
+ shipMiniBox('overview-hit-box', false, 'KD', fmtFix(b.kd, 2))
+ '                </div>\n'
+ '            </div>\n'
+ '        </div>\n';
    }

    /* 「战斗类型」表里的一行（模板里四段 {% if %} 各写一遍，排版相同）。
       表头复用用户页那个 buildInfoHead —— 两张表的列与顺序完全一样
       （类型 / 场次 / 胜率 / [PR] / 场均 / 击杀 / 存活 / 命中）。 */
    function shipInfoRow(name, b, showPr) {
        return '            <div class="information-col">\n'
+ '                <div class="information-col-item">' + name + '</div>\n'
+ '                <div class="information-col-item">' + fmtRaw(b.battle) + '</div>\n'
+ '                <div class="information-col-item" style="color: ' + b.winColor + ';">' + fmtFix(b.win, 2) + '%</div>\n'
+ (showPr ? '                <div class="information-col-item" style="color: ' + b.prColor + ';">' + fmtRaw(b.pr) + '</div>\n' : '')
+ '                <div class="information-col-item" style="color: ' + b.damageColor + ';">' + fmtInt(b.damage) + '</div>\n'
+ '                <div class="information-col-item">' + fmtFix(b.frags, 2) + '</div>\n'
+ '                <div class="information-col-item">' + fmtFix(surviveRatio(b), 1) + '%</div>\n'
+ '                <div class="information-col-item">' + fmtFix(b.hitMain, 2) + '%</div>\n'
+ '            </div>\n';
    }

    /* 最高记录里的一格。 */
    function shipFrag(k, v) {
        return '                <div class="frag-item one-background-color">\n'
+ '                    <div class="frag-key">' + k + '</div>\n'
+ '                    <div class="frag-value">' + v + '</div>\n'
+ '                </div>\n';
    }

    function buildShipFixture(base, uid, ship) {
        var d = ship || DEMO_SHIP;                 // 没有真实数据 → 演示快照
        var u = d.userInfo || {};
        var ti = d.typeInfo || {};
        var pvp = ti.PVP || {};
        var showPr = infoNum(u.prStatus) !== 1;

        /* 口径照抄模板：
             PR 条 —— prStatus != 1 才画，取的是「PVP 打过就用 PVP，否则退排位」
                      那个内联三元（**没有** value > 0 这一层判断，与用户页不同）；
             核心数据 —— 同样是 PVP 优先、退排位。
           typeInfo[bt].battle 是布尔标记，判的就是「打没打过」。 */
        var mainKey = pvp.battle ? 'PVP' : 'RANK_SOLO';
        var main = shipBattleOf(ti[mainKey]);
        var prBlock = showPr
            ? buildPr({value: main.pr, name: main.prName, color: main.prColor}) + '\n'
            : '';

        /* 最后战斗时间**只读 PVP**（模板里写死了 data['typeInfo']['PVP']，
           即使上面退到了排位也一样）—— 别顺手改成读 mainKey。 */
        var last = infoNum((pvp.battleInfo || {}).lastBattleTime);
        var lastText = last > 0 ? fmtTime(last) : 'N/A';

        var battleRows = '';
        SHIP_BATTLE_ROWS.forEach(function (t) {
            var tb = ti[t[0]] || {};
            if (tb.battle) battleRows += shipInfoRow(t[1], shipBattleOf(tb), showPr);
        });

        /* 最高记录 / 服务器数据两块也只读 PVP（模板同款写死）。 */
        var mx = (pvp.battleInfo || {}).maxInfo || {};
        function maxVal(k) { return fmtRaw((mx[k] || {}).value); }
        var origin = ((((pvp.battle ? ti.PVP : ti.RANK_SOLO) || {}).prInfo || {}).details || {}).originalServer || {};

        return fixtureShell(base, uid,
            headerBlock()
+ '\n'
+ shipHeaderBlock(d.shipInfo)
+ '\n'
+ prBlock
+ '        <div class="recnet-time">\n'
+ '            <span>最后战斗时间：</span>\n'
+ '            <span>' + lastText + '</span>\n'
+ '        </div>\n'
+ '\n'
+ shipOverview(main)
+ '\n'
+ '        <div class="random-header one-background-color">战斗类型</div>\n'
+ '        <div class="information-body one-background-color data-battle-type">\n'
+ buildInfoHead(showPr)
+ battleRows
+ '        </div>\n'
+ '\n'
+ '        <div class="random-header one-background-color">最高记录</div>\n'
+ '        <div class="frag-data">\n'
+ '            <div class="frag-data-col">\n'
+ shipFrag('伤害', maxVal('maxDamageDealt'))
+ shipFrag('潜在', maxVal('maxTotalAgro'))
+ shipFrag('侦查', maxVal('maxScoutingDamage'))
+ '            </div>\n'
+ '            <div class="frag-data-col">\n'
+ shipFrag('击杀', maxVal('maxFrags'))
+ shipFrag('飞机数', maxVal('maxPlanesKilled'))
+ shipFrag('经验', maxVal('maxXp'))
+ '            </div>\n'
+ '        </div>\n'
+ '\n'
+ '        <div class="random-header one-background-color">服务器数据</div>\n'
+ '        <div class="information-body one-background-color">\n'
+ '            <div class="information-col">\n'
+ '                <div class="information-col-item">场均</div>\n'
+ '                <div class="information-col-item">胜率</div>\n'
+ '                <div class="information-col-item">击杀</div>\n'
+ '            </div>\n'
+ '            <div class="information-col">\n'
+ '                <div class="information-col-item">' + fmtFix(origin.damage, 2) + '</div>\n'
+ '                <div class="information-col-item">' + fmtFix(origin.wins, 2) + '</div>\n'
+ '                <div class="information-col-item">' + fmtFix(origin.frags, 2) + '</div>\n'
+ '            </div>\n'
+ '        </div>\n',
            '');   // 单船页没有图表，尾部不用引 echarts
    }

    /* =====================================================
       预览支持的模板 —— 页面顶栏那个下拉框的数据源。
       加一个模板 = 这里加一行 + 写一个 buildXxxFixture()（结构照抄对应模板），
       页面侧不用改（下拉框是按这张表现拼的）。
       ▍两个模板共用**同一份头部**（headerBlock），所以头像设置 / 卡片旋钮 /
         大背景图这些设置切来切去都照样生效 —— 它们改的是同一套类名。
       ===================================================== */
    var TEMPLATES = {
        info: {
            label: '用户信息 info',
            brand: 'info-v6 / userInfo',
            build: function (base, uid, data) { return buildFixture(base, uid, data); }
        },
        ship: {
            label: '单船 ship',
            brand: 'ship-v6 / 单船',
            build: function (base, uid, data) { return buildShipFixture(base, uid, data); }
        }
    };

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
        /* 当前预览哪个模板（info / ship），换模板走 setTemplate()。 */
        this.template = TEMPLATES[opts.template] ? opts.template : 'info';
        /* 页面里那些**真实战力数据**（场次 / 胜率 / PR / 图表…）——
           就是 /public/wows/account/user/info2 的 data；null = 用内置演示快照。
           换数据走 setInfoData()，那是重建文档而不是改节点。 */
        this.infoData = opts.info || null;
        /* 单船页的数据（/public/wows/account/ship/info 的 data），同上走 setShipData()。 */
        this.shipData = opts.ship || null;

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
        frame.srcdoc = this._fixtureHtml();
    };

    /* 当前该往 iframe 里塞哪份 fixture。
       ▍opts.fixture 是「整份 fixture 由调用方给」的老口子（谁传谁负责），
         不传就按当前模板 + 该模板的数据现场生成。 */
    HikariUserPreview.prototype._fixtureHtml = function () {
        if (this.opts.fixture) return this.opts.fixture;
        var t = TEMPLATES[this.template] || TEMPLATES.info;
        return t.build(this.assetBase, this.uid,
            this.template === 'ship' ? this.shipData : this.infoData);
    };

    /* 重建 iframe 文档 —— 换模板、换数据都走这里。
       ▍为什么是重建而不是改节点：信息区块（ship_header / PR 条 / 核心数据 /
         两张表 / 最高记录 / 图表）在成品里就是**按数据排版**的 —— 行数、
         有没有 PR 条、图表的两条曲线都随数据变，逐节点去改只会把
         「预览即成品」搞丢；换模板更是整棵 DOM 都不一样。
       ▍重建后 iframe 会自己再走一次 _bindFrame，render() 拿 _lastUserInfo
         把头部那几块（头像 / 彩色名 / 签名 / 服务器行）补回来，
         所以调用方**不需要**再 render 一次，头像设置也不会丢。
       ▍先关掉 ready：旧文档里那些节点马上就不作数了，
         免得 fit() / getStageSize() 在空档里量到上一份页面的高度。 */
    HikariUserPreview.prototype._rebuild = function () {
        this.ready = false;
        this.doc = null;
        this.dom = null;
        this.frameEl.srcdoc = this._fixtureHtml();
    };

    /* 换预览模板。同名不重建（音调用方可能在 change 事件里重复调）。 */
    HikariUserPreview.prototype.setTemplate = function (name) {
        if (!TEMPLATES[name] || name === this.template) return;
        this.template = name;
        this._rebuild();
    };

    HikariUserPreview.prototype.getTemplate = function () {
        return this.template;
    };

    /* 换一份「用户 v2 数据」（info2 的 data）并重建预览。
       ▍传 null（或不传）＝回到演示快照。 */
    HikariUserPreview.prototype.setInfoData = function (info) {
        this.infoData = info || null;
        this._rebuild();
    };

    HikariUserPreview.prototype.getInfoData = function () {
        return this.infoData;
    };

    /* 换一份单船数据（/public/wows/account/ship/info 的 data）并重建预览。 */
    HikariUserPreview.prototype.setShipData = function (data) {
        this.shipData = data || null;
        this._rebuild();
    };

    HikariUserPreview.prototype.getShipData = function () {
        return this.shipData;
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
               背景位置 / 尺寸写成**独立长手属性**，单值会套用到所有图层，写一次即可。
               ▍位置的两个维度来源不同（这是刻意的，别合并）：
                  横向 = crop.x          —— 裁剪器拖出来的，**目前只有预览认**（宏里恒 center）
                  纵向 = 固定 0（贴顶）  —— 不可配，与宏里的 poster_pos_y 同值，
                                          见 POSTER_POS_Y_TOP 的注释 */
            var opacity = posterOpacity(poster);   // dark 是「透明度」，这里换算成 CSS 不透明度
            var maskAlpha = posterMaskAlpha(opacity);
            css.push('.main-content {\n'
                + '    position: relative;\n'
                + cardVarsCss(av.card)              // 毛玻璃元素块的两个旋钮（与宏同构）
                + '}\n\n'
                + '.main-content::before {\n'
                + '    content: "";\n'
                + '    position: absolute;\n'
                + '    inset: 0;\n'
                + '    z-index: -1;\n'
                + '    opacity: ' + opacity + '%;\n'
                + '    background: linear-gradient(rgba(0, 0, 0, ' + maskAlpha + '), rgba(0, 0, 0, ' + maskAlpha + ')),\n'
                + '                url("' + poster.data + '") no-repeat;\n'
                + '    background-position: ' + cropPosX(poster) + '% ' + POSTER_POS_Y_TOP + '%;\n'
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
         poster 纵向位置        -> .main-content::before 的 background-position 纵向，
                                  固定贴顶（0%）。**不读数据**，见 POSTER_POS_Y_TOP；
                                  只在页高 < 2250px 的短页上看得出来。
         avatar.card.dark/blur  -> .main-content 的 --card-alpha / --card-blur
                                  （只在该页有海报时下发；见 cardVarsCss）。
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

       ▍「自由比例 ↔ 固定宽高」（banner / poster 可在弹窗里切，见 setAspectLock）：
         · 自由比例（默认）：框的宽高比随便拉 —— 模板那边 background-size
           只给宽度（100%）或 cover，比例本来就无所谓。
         · 固定宽高：框锁成 lockFrame 的比例（小背景 1400×300、
           大背景 1500×2600），手柄只能等比拉 —— 想要「框到什么就是什么」时用。
         切模式会重算 _sizeDefault 但保住 scale，所以缩放滑块不会乱跳。

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
        /* lockFrame：「固定宽高」模式下裁剪框锁的那个比例。
           默认跟 frame 一致（头像 250×250、小背景 1400×300 都够用）。
           大背景图必须**单独给**：它的 frame 会被 setFrame() 改成**实时页高**
           （自由比例下的位置换算必须用真实盒子比例），而用户要的「固定宽高」
           是一个不随页高浮动的常量 1500×2600 —— 两者不是一回事，不能共用。
           ▍锁定时 frame 其实完全不参与运算（位置/基准都只走 lockAspect），
           所以这两个值分开存是安全的。 */
        this.lockFrame = opts.lockFrame
            ? { w: opts.lockFrame.w, h: opts.lockFrame.h }
            : { w: this.frame.w, h: this.frame.h };
        this.lockAspect = this.lockFrame.w / this.lockFrame.h;
        /* freeAspect: 裁剪框不锁宽高比，手柄随便拉。
           适合模板里本来就「不在乎图片比例」的槽位：
             · 小背景图 background-size: 100%  -> 宽度撑满，高度多余部分被裁
             · 大背景图 background-size: cover -> 等比放大到盖住整个盒子
           头像那种固定方框（250×250）就必须锁 1:1，否则画面会变形。
           ▍banner / poster 默认 true，但可以在弹窗里用「自由比例 ↔ 固定宽高」
           按钮切到锁比例（见 setAspectLock）。 */
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
            // 锁比例时用 lockAspect（「固定宽高」）；freeAspect 时用 NaN（Cropper 的「自由」）
            aspectRatio: this.freeAspect ? NaN : this.lockAspect,
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
            h = w / this.lockAspect;
        }
        if (h > nh) {
            var k = w / h;       // 先留住当前宽高比，别被下面的赋值带跑
            h = nh;
            w = h * (this.freeAspect ? k : this.lockAspect);
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
        /* 只有锁比例时才需要跟着改框、重算基准 —— 而且改的是**锁定的那个比例**
           （lockAspect），不是模板盒子比例 ar：poster 的 frame 会随页高浮动，
           锁定的固定宽高不能被它带跑。
           自由比例下框是用户自己拉的；而且 _sizeDefault 不能每次重算 ——
           预览的页面高度一浮动（poster 的 frame.h 就是这么来的），scale 会跟着抖，
           缩放滑块看着就乱跳。
           （对 poster 来说这个分支基本是空转：lockAspect 是常量，
             setAspectRatio 进去也是同一个值。） */
        if (!this.freeAspect && changed && this.cropper) {
            this.cropper.setAspectRatio(this.lockAspect);
            this._sizeDefault = this._measureSize();
        }
        /* 页高变了要顺手重画 meta —— 那一行里写着「取景框比例 1500×H」，
           不重画它就永远停在第一次的值上（setFrame 由 syncPosterFrame() 在
           每次 render() 时调用，但 _renderMeta 只在 crop / relayout 时才跑）。 */
        if (changed) this._renderMeta();
        return this;
    };

    /* 切「自由比例 ↔ 固定宽高」。
       locked = true  → 框锁成 lockFrame 的比例，手柄只能等比拉
       locked = false → 自由比例，宽高比随便拉（banner / poster 的默认）
       ▍切换时两件事一起做，否则用户会看到「跳一下」：
         1) 换模式后重算 _sizeDefault —— 两种模式的基准算法不同
            （自由 = 刚好盖住模板盒子的那个框；固定 = Cropper 给的最大等比框）
         2) 用同一个 scale 把框写回去，保住用户已经调好的缩放；
            x/y 也一并带过去，免得切一下图就跑到别处。
       未就绪（弹窗没打开 / 还没选图）时只改模式标记，等 _onReady 自己按新算。 */
    HikariImageCropper.prototype.setAspectLock = function (locked) {
        locked = !!locked;
        if (locked === !this.freeAspect) return this;      // 已经是这个状态
        var p = this.getPosition();
        this.freeAspect = !locked;
        /* 自由比例下框的比例由 _boxRatio 决定 —— 切回来时先归位到「刚好盖住盒子」的比例。
           ▍这句**必须放在下面的 ready 早退之前**：还没就绪（弹窗没开 / 没选图）时
           我们就退出了，但 _boxRatio 得先归位，否则等 _onReady 跑起来会拿着
           锁定模式残留的框比例去写自由模式的框，比例就是歪的。 */
        if (this.freeAspect) this._boxRatio = this.aspect;
        if (!this.ready || !this.cropper) return this;

        this.cropper.setAspectRatio(this.freeAspect ? NaN : this.lockAspect);
        /* ▍切回自由比例后，_boxRatio **必须在这里再归位一次**。
           原因：setAspectRatio(NaN) 内部会走 initCropBox() 把裁剪框重置，
           而 aspectRatio 是 NaN 时它退回按**原图**的宽高比算 ——
           重置会触发 crop 事件 -> _emit() -> `_boxRatio = 当前框的比例`，
           于是我们上面刚设好的「刚好盖住模板盒子」的比例被改成了图片比例。
           后果（实测）：本地 1600×1200 的图配 1500×2600 的框，
           自由模式的框本应是 692×1200，结果被写成 692×520（图片比例），
           预览里的 background-position 也从 50% 跳到 100% ——
           用户的裁剪构图直接被改掉，看着就是「切回去之后裁剪失效了」。
           所以这次归位要放在 setAspectRatio 之后、_writePos 之前。 */
        if (this.freeAspect) this._boxRatio = this.aspect;
        this._sizeDefault = this._measureDefault();
        this._targetPos = { x: p.x, y: p.y, scale: p.scale };
        this._writePos();
        /* ▍这里必须显式重画一次 meta：紧接的 _emit() 里，_applyEmit 会拿位置去重
           （x/y/size 都没变就直接 return），于是「裁剪框 自由比例/固定xx」那一栏
           会停在旧文案上 —— 按钮已经写「固定宽高」、meta 还写「自由比例」，自相矛盾。 */
        this._renderMeta();
        this._emit();
        return this;
    };

    HikariImageCropper.prototype.isAspectLocked = function () {
        return !this.freeAspect;
    };

    HikariImageCropper.prototype._renderMeta = function (p) {
        var parts = [];
        parts.push('取景框比例 <b>' + this.frame.w + '×' + this.frame.h + '</b>');
        // 裁剪框模式：自由比例 / 固定宽高（固定时把锁的那个尺寸写出来）
        parts.push('裁剪框 <b>' + (this.freeAspect
            ? '自由比例'
            : ('固定 ' + this.lockFrame.w + '×' + this.lockFrame.h)) + '</b>');
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
    /* 可预览的模板表（键 + label + brand）—— 设置页顶栏那个下拉框按它拼，
       这样「加模板」只需要改组件一处。 */
    global.HikariUserPreview.TEMPLATES = TEMPLATES;
    global.HikariImageCropper = HikariImageCropper;

    global.HikariBuild = HIKARI_BUILD;
}(typeof window !== 'undefined' ? window : this));
