let pr_number = document.querySelector('.pr-number').innerText;
pr_number = parseInt(pr_number);
let color = "";
// 重构
const getPrColor = (pr) => {
    if (pr === 0) {
        return "rgb(130, 130, 130)"; // #828282
    } else if (pr < 750) {
        return "rgb(244, 67, 54)"; // #F44336
    } else if (pr < 1100) {
        return "rgb(255, 152, 0)"; // #FF9800
    } else if (pr < 1350) {
        return "rgb(255, 193, 7)"; // #FFC107
    } else if (pr < 1550) {
        return "rgb(139, 195, 74)"; // #8BC34A
    } else if (pr < 1750) {
        return "rgb(76, 175, 80)"; // #4CAF50
    } else if (pr < 2100) {
        return "rgb(0, 188, 212)"; // #00BCD4
    } else if (pr < 2450) {
        return "rgb(156, 39, 176)"; // #9C27B0
    } else {
        return "rgb(103, 58, 183)"; // #673AB7
    }
};

color = getPrColor(pr_number);

document.querySelector(".pr").style.background = "linear-gradient(90deg, " +
    "rgba" + color.slice(3, -1) + ", 0.6), " +
    "rgba" + color.slice(3, -1) + ", 0.8), " +
    "rgba" + color.slice(3, -1) + ", 0.9), " +
    "rgba" + color.slice(3, -1) + ", 1), " +
    "rgba" + color.slice(3, -1) + ", 0.9), " +
    "rgba" + color.slice(3, -1) + ", 0.8), " +
    "rgba" + color.slice(3, -1) + ", 0.6))"
document.querySelector(".pr").style.color = "#333333ff";


//调整工会默认颜色
const firstSpan = document.querySelector('.user-info span:first-child');

if (firstSpan) {
    // 获取内联样式或计算样式
    const color =  getComputedStyle(firstSpan).color;

    // 检查颜色是否包含 b3b3b3
    if ( color === 'rgb(179, 179, 179)') {
        firstSpan.style.color = '#000000'; // 改为黑色
    }
}

const clanUserServer = document.querySelector('.clan-user-server');
const userSignature = document.querySelector('.user-signature');

if (!userSignature && clanUserServer) {
    clanUserServer.style.gap = '45px';
}

information_col(document.querySelectorAll('.data-battle-type > .information-col'))
information_col(document.querySelectorAll('.data-battle-type > .ship-data-col'))
// 未来弃用
information_col(document.querySelectorAll('.data-ship-type > .information-col'))

function information_col(arr_information) {
    for (let i = 0; i < arr_information.length; i++) {
        arr_information[i].classList.add('two-background-color');
        if (i === 0) {
            arr_information[i].classList.add('two-background-color');
            arr_information[i].style.borderTopLeftRadius = "16px";
            arr_information[i].style.borderTopRightRadius = "16px";
        } else if (i % 2 === 0) {
            arr_information[i].classList.add('two-background-color');
        }
        //最后一行
        if (i === (arr_information.length - 1)) {
            arr_information[i].style.borderBottomLeftRadius = "16px";
            arr_information[i].style.borderBottomRightRadius = "16px";
        }
    }
}

const el = document.querySelector('.main-content');
const hasAnyBackground = el && window.getComputedStyle(el).backgroundImage !== 'none';
console.log('是否有背景图:', hasAnyBackground);
if (!hasAnyBackground) {
    // 创建style元素
    const styleElement = document.createElement('style');
    // 添加CSS规则
    styleElement.textContent = `
            .one-background-color {
                background: #F2F2F2;
                backdrop-filter: none;
                -webkit-backdrop-filter: none;
                border: 2px solid #CCCCCC;
                box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
            }
            
            .two-background-color {
                background: #F2F2F2;
                border: 1px solid #CCCCCC;
                position: relative;
                z-index: 1;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            }
            .main-content{
                background: #FDFDFD;
            }
        `;

    // 添加到head
    document.head.appendChild(styleElement);
    let rh = document.querySelectorAll('.random-header')
    for (let i = 0; i < rh.length; i++) {
        rh[i].classList.remove('one-background-color')
        rh[i].classList.add('three-background-color');
    }
    let rh1 = document.querySelectorAll('.recent-battle-data-title')
    rh1[0].classList.add('three-background-color');
    rh1[0].style.borderTopLeftRadius = '16px';
    rh1[0].style.borderTopRightRadius = '16px';
    rh1[1].classList.add('three-background-color');
    rh1[1].style.borderBottomLeftRadius = '16px';
    rh1[1].style.borderBottomRightRadius = '16px';
}

// 数据变化动态颜色填充
const changeAvgDmgElement = document.querySelector(".change-avgdmg");
const changeWinElement = document.querySelector(".change-win");
const changePrElement = document.querySelector(".change-pr");

// 处理平均伤害变化
if (changeAvgDmgElement) {
    let change_avgdmg = parseInt(changeAvgDmgElement.innerText);

    if (change_avgdmg > 0) {
        changeAvgDmgElement.style.color = "#70AD47";
        changeAvgDmgElement.innerText = "+" + change_avgdmg;
    } else if (change_avgdmg < 0) {
        changeAvgDmgElement.style.color = "#FF0000";
    } else {
        changeAvgDmgElement.style.color = "#666666"; // 0值可以用灰色
    }
}

// 处理胜率变化
if (changeWinElement) {
    let change_win = parseFloat(changeWinElement.innerText.split("%", 1)[0]);
    if (change_win > 0) {
        changeWinElement.style.color = "#70AD47";
        changeWinElement.innerText = "+" + change_win + "%";
    } else if (change_win < 0) {
        changeWinElement.style.color = "#FF0000";
        changeWinElement.innerText = change_win + "%";
    } else {
        changeWinElement.style.color = "#666666";
        changeWinElement.innerText = change_win + "%";
    }
}

// 处理PR变化
if (changePrElement) {
    let change_pr = parseInt(changePrElement.innerText);

    if (change_pr > 0) {
        changePrElement.style.color = "#70AD47";
        changePrElement.innerText = "+" + change_pr;
    } else if (change_pr < 0) {
        changePrElement.style.color = "#FF0000";
    } else {
        changePrElement.style.color = "#666666";
    }
}

