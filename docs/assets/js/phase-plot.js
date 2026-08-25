(function (global) {
  'use strict';

  const CONFIG = Object.freeze({
    RECENT_WINDOW_MONTHS: 12,
    HISTORY_LABEL: 'Earlier record',
    RECENT_LABEL: 'Latest 12 months',
    CURRENT_LABEL: 'Current position',
    RECENT_COLOR: '#dc2626',
    CURRENT_COLOR: '#ffbf00',
    MONTHLY_POINT_RADIUS: 2.6,
    CURRENT_POINT_RADIUS: 5.2
  });

  function xMap(value, plot, domain) {
    return plot.l + (value - domain.xmin) / (domain.xmax - domain.xmin) * (plot.r - plot.l);
  }

  function yMap(value, plot, domain) {
    return plot.b - (value - domain.ymin) / (domain.ymax - domain.ymin) * (plot.b - plot.t);
  }

  function drawBackground(ctx, width, height, plot, domain, labels, ticks, axisStyle) {
    const style = axisStyle || {};
    const mx = value => xMap(value, plot, domain);
    const my = value => yMap(value, plot, domain);
    const formatX = style.formatX || (value => String(value));
    const formatY = style.formatY || (value => value.toFixed(0));

    ctx.fillStyle = style.background || '#0a0a0e';
    ctx.fillRect(0, 0, width, height);
    ctx.strokeStyle = style.gridColor || '#1a1a2a';
    ctx.lineWidth = 0.5;

    if (ticks) {
      ticks.x.forEach(value => {
        ctx.beginPath(); ctx.moveTo(mx(value), plot.t); ctx.lineTo(mx(value), plot.b); ctx.stroke();
      });
      ticks.y.forEach(value => {
        ctx.beginPath(); ctx.moveTo(plot.l, my(value)); ctx.lineTo(plot.r, my(value)); ctx.stroke();
      });
    } else {
      for (let value = Math.ceil(domain.xmin); value <= Math.floor(domain.xmax); value += 1) {
        ctx.beginPath(); ctx.moveTo(mx(value), plot.t); ctx.lineTo(mx(value), plot.b); ctx.stroke();
      }
      for (let value = Math.ceil(domain.ymin); value <= Math.floor(domain.ymax); value += 1) {
        ctx.beginPath(); ctx.moveTo(plot.l, my(value)); ctx.lineTo(plot.r, my(value)); ctx.stroke();
      }
    }

    ctx.strokeStyle = style.zeroColor || 'rgba(180,180,180,0.6)';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    const xZero = mx(0);
    if (xZero >= plot.l && xZero <= plot.r) {
      ctx.beginPath(); ctx.moveTo(xZero, plot.t); ctx.lineTo(xZero, plot.b); ctx.stroke();
    }
    const yZero = my(0);
    if (yZero >= plot.t && yZero <= plot.b) {
      ctx.beginPath(); ctx.moveTo(plot.l, yZero); ctx.lineTo(plot.r, yZero); ctx.stroke();
    }
    ctx.setLineDash([]);

    ctx.strokeStyle = style.borderColor || '#363650';
    ctx.strokeRect(plot.l, plot.t, plot.r - plot.l, plot.b - plot.t);

    ctx.fillStyle = style.tickColor || '#555568';
    ctx.font = style.tickFont || '10px monospace';
    ctx.textAlign = 'center';
    if (ticks) {
      ticks.x.forEach(value => ctx.fillText(formatX(value), mx(value), plot.b + (style.tickOffset || 14)));
    } else {
      for (let value = Math.ceil(domain.xmin); value <= Math.floor(domain.xmax); value += 2) {
        ctx.fillText(formatX(value), mx(value), plot.b + (style.tickOffset || 14));
      }
    }

    ctx.fillStyle = style.labelColor || '#3a3a50';
    ctx.font = style.labelFont || '10px monospace';
    ctx.fillText(labels.x, (plot.l + plot.r) / 2, style.xLabelY || height - 3);

    ctx.textAlign = 'right';
    ctx.fillStyle = style.tickColor || '#555568';
    ctx.font = style.tickFont || '10px monospace';
    if (ticks) {
      ticks.y.forEach(value => ctx.fillText(formatY(value), plot.l - 7, my(value) + 4));
    } else {
      for (let value = Math.ceil(domain.ymin); value <= Math.floor(domain.ymax); value += 1) {
        ctx.fillText(formatY(value), plot.l - 7, my(value) + 4);
      }
    }

    ctx.save();
    ctx.fillStyle = style.labelColor || '#3a3a50';
    ctx.translate(style.yLabelX || 11, (plot.t + plot.b) / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = 'center';
    ctx.font = style.labelFont || '10px monospace';
    ctx.fillText(labels.y, 0, 0);
    ctx.restore();
  }

  function compositeFrame(ctx, width, height, plot, domain, historyCanvas, tail, timeLabel) {
    const mx = value => xMap(value, plot, domain);
    const my = value => yMap(value, plot, domain);
    ctx.drawImage(historyCanvas, 0, 0);

    const count = tail.length;
    for (let index = 1; index < count; index += 1) {
      const fraction = index / count;
      ctx.beginPath();
      ctx.strokeStyle = 'rgba(255,59,48,' + (0.65 + 0.35 * fraction).toFixed(2) + ')';
      ctx.lineWidth = 1.6 + 0.9 * fraction;
      ctx.moveTo(mx(tail[index - 1].x), my(tail[index - 1].y));
      ctx.lineTo(mx(tail[index].x), my(tail[index].y));
      ctx.stroke();
    }

    for (const point of tail) {
      if (point.irest === 0) {
        ctx.beginPath();
        ctx.arc(mx(point.x), my(point.y), CONFIG.MONTHLY_POINT_RADIUS, 0, 2 * Math.PI);
        ctx.fillStyle = '#ff3b30';
        ctx.fill();
        ctx.strokeStyle = 'rgba(255,255,255,0.9)';
        ctx.lineWidth = 0.8;
        ctx.stroke();
      }
    }

    if (count > 0) {
      const current = tail[count - 1];
      const cx = mx(current.x);
      const cy = my(current.y);
      const radius = Math.max(CONFIG.CURRENT_POINT_RADIUS, (Number(global.G_DOT) || 3) + 2);
      ctx.beginPath(); ctx.arc(cx, cy, radius + 5, 0, 2 * Math.PI);
      ctx.fillStyle = 'rgba(255,191,0,0.20)'; ctx.fill();
      ctx.beginPath(); ctx.arc(cx, cy, radius, 0, 2 * Math.PI);
      ctx.fillStyle = CONFIG.CURRENT_COLOR; ctx.fill();
      ctx.strokeStyle = '#fff3bf'; ctx.lineWidth = 1.5; ctx.stroke();
    }

    if (timeLabel) {
      ctx.font = 'bold 13px monospace';
      const textWidth = ctx.measureText(timeLabel).width;
      ctx.fillStyle = 'rgba(10,10,20,0.72)';
      ctx.beginPath();
      ctx.roundRect(plot.l + 6, plot.t + 6, textWidth + 16, 22, 4);
      ctx.fill();
      ctx.fillStyle = '#e8e8f0';
      ctx.textAlign = 'left';
      ctx.fillText(timeLabel, plot.l + 14, plot.t + 22);
    }
  }

  function addHistorySegment(ctx, x1, y1, x2, y2, month, plot, domain) {
    ctx.beginPath();
    ctx.strokeStyle = typeof global.seasonColorAlpha === 'function'
      ? global.seasonColorAlpha(month, 0.35)
      : 'rgba(119,119,119,0.35)';
    ctx.lineWidth = 0.9;
    ctx.moveTo(xMap(x1, plot, domain), yMap(y1, plot, domain));
    ctx.lineTo(xMap(x2, plot, domain), yMap(y2, plot, domain));
    ctx.stroke();
  }

  function recentWindowStartYM(currentYM) {
    return currentYM - (CONFIG.RECENT_WINDOW_MONTHS - 1);
  }

  function pushRecentPoint(tail, point, drawHistory) {
    tail.push(point);
    const firstRecentYM = recentWindowStartYM(point.ym);
    while (tail.length > 1 && tail[0].ym < firstRecentYM) {
      const oldest = tail.shift();
      drawHistory(oldest, tail[0]);
    }
  }

  function pushObservedPoint(tail, x, y, year, month, irest, historyCtx, plot, domain) {
    const point = {x, y, year, month, irest: Number(irest) || 0, ym: year * 12 + month};
    pushRecentPoint(tail, point, (oldest, next) => {
      addHistorySegment(historyCtx, oldest.x, oldest.y, next.x, next.y, oldest.month, plot, domain);
    });
  }

  function pushFixedPoint(tail, x, y, month, length, historyCtx, plot, domain) {
    tail.push({x, y, month, irest: null});
    if (tail.length > length) {
      addHistorySegment(
        historyCtx, tail[0].x, tail[0].y, tail[1].x, tail[1].y, tail[0].month, plot, domain
      );
      tail.shift();
    }
  }

  function makeOffscreen(width, height) {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    return canvas;
  }

  function installGlobals() {
    global.drawBg = drawBackground;
    global.compositeFrame = compositeFrame;
    global.addToOff = addHistorySegment;
    global.makeOff = makeOffscreen;
  }

  global.EnsoPhasePlot = Object.freeze({
    CONFIG,
    drawBackground,
    compositeFrame,
    addHistorySegment,
    recentWindowStartYM,
    pushRecentPoint,
    pushObservedPoint,
    pushFixedPoint,
    makeOffscreen,
    installGlobals
  });
})(window);
