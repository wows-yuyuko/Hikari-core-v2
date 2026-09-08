// ==========================================================
// wws-info-v6 交互脚本
// 与 v5 的差异：v2 接口不再返回 dwpData，删除变化值计算逻辑；
// 表格斑马纹 / 分隔线由 CSS 内建，不再用 JS 逐行叠加玻璃条。
// ==========================================================

// 军团标签颜色修正：无有效颜色（#b3b3b3 默认灰）时改为黑色
const firstSpan = document.querySelector('.user-info span:first-child');

if (firstSpan) {
    const color = getComputedStyle(firstSpan).color;
    if (color === 'rgb(179, 179, 179)') {
        firstSpan.style.color = '#000000'; // 改为黑色
    }
}

// 无签名时加大信息列间距，避免下部悬空
const clanUserServer = document.querySelector('.clan-user-server');
const userSignature = document.querySelector('.user-signature');

if (!userSignature && clanUserServer) {
    clanUserServer.style.gap = '40px';
}

// 无海报背景时切换浅色主题（毛玻璃改为实色，保证文字可读）
const el = document.querySelector('.main-content');
const hasAnyBackground = el && window.getComputedStyle(el).backgroundImage !== 'none';

if (!hasAnyBackground) {
    const styleElement = document.createElement('style');
    styleElement.textContent = `
        .main-content { background: #FCFCFE; }
        .one-background-color {
            background: #F5F3FA;
            backdrop-filter: none;
            -webkit-backdrop-filter: none;
            border: 1.5px solid #DCD5EE;
            box-shadow: 0 2px 10px rgba(80, 70, 120, 0.08);
        }
        .information-body {
            background: #FFFFFF;
            border-color: #E4DDF2;
            box-shadow: 0 2px 10px rgba(80, 70, 120, 0.06);
        }
        .information-col + .information-col { border-top-color: #EFEAF8; }
        .information-col.header-col { background: #F5F3FA; }
        .information-col:not(.header-col):nth-child(even) { background: #FAF8FE; }
        .random-header {
            background: #F5F3FA;
            border-color: #DCD5EE;
            box-shadow: none;
            color: #4a4a5a;
        }
        .chart-box {
            background: #FFFFFF;
            border-color: #E4DDF2;
        }
        .recnet-time { color: #6b7080; }
        .footer { color: #8a8f9c; }
        .footer p { text-shadow: none; }
    `;
    document.head.appendChild(styleElement);
}
