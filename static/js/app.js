/* AllClad – Frontend JavaScript
   ================================================================ */

// ── Sidebar Toggle (iPad / Mobile) ─────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.getElementById('sidebarToggle');
  const sidebar = document.getElementById('sidebar');

  if (toggle && sidebar) {
    toggle.addEventListener('click', (e) => {
      e.stopPropagation();
      sidebar.classList.toggle('open');
    });

    // Close sidebar on outside tap (iPad)
    document.addEventListener('click', (e) => {
      if (sidebar.classList.contains('open') && !sidebar.contains(e.target)) {
        sidebar.classList.remove('open');
      }
    });

    // Swipe to open sidebar
    let touchStartX = 0;
    document.addEventListener('touchstart', (e) => {
      touchStartX = e.touches[0].clientX;
    }, { passive: true });

    document.addEventListener('touchend', (e) => {
      const touchEndX = e.changedTouches[0].clientX;
      const diff = touchEndX - touchStartX;
      if (touchStartX < 30 && diff > 60) {
        sidebar.classList.add('open');
      } else if (sidebar.classList.contains('open') && diff < -60) {
        sidebar.classList.remove('open');
      }
    }, { passive: true });
  }

  // ── Auto-dismiss flash messages with smooth exit ───────────────
  document.querySelectorAll('.flash').forEach(flash => {
    setTimeout(() => {
      flash.style.transition = 'all .4s cubic-bezier(.4,0,.2,1)';
      flash.style.opacity = '0';
      flash.style.transform = 'translateY(-10px) scale(.95)';
      setTimeout(() => flash.remove(), 400);
    }, 5000);
  });

  // ── Dashboard: submit search on Enter ──────────────────────────
  const searchInput = document.querySelector('.filters-bar input[name="q"]');
  if (searchInput) {
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        document.getElementById('filtersForm').submit();
      }
    });
  }

  // ── Stat card hover counter animation ──────────────────────────
  document.querySelectorAll('.stat-number').forEach(el => {
    const target = parseInt(el.textContent);
    if (isNaN(target) || target === 0) return;
    el.textContent = '0';
    animateCounter(el, 0, target, 600);
  });

  // ── Confetti on success flash (calibration logged!) ────────────
  const successFlash = document.querySelector('.flash-success');
  if (successFlash && successFlash.textContent.includes('Calibration logged')) {
    spawnConfetti();
  }

  // ── Periodic alert check (every 60s) ───────────────────────────
  setInterval(checkAlerts, 60000);
});


// ── Counter Animation ────────────────────────────────────────────
function animateCounter(el, start, end, duration) {
  const startTime = performance.now();
  function update(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);
    // Ease out cubic
    const eased = 1 - Math.pow(1 - progress, 3);
    el.textContent = Math.round(start + (end - start) * eased);
    if (progress < 1) requestAnimationFrame(update);
  }
  requestAnimationFrame(update);
}


// ── Confetti 🎉 ──────────────────────────────────────────────────
function spawnConfetti() {
  const colors = ['#7c3aed', '#06b6d4', '#22c55e', '#f59e0b', '#ef4444', '#ec4899', '#6366f1'];
  const container = document.createElement('div');
  container.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:9999;overflow:hidden;';
  document.body.appendChild(container);

  for (let i = 0; i < 40; i++) {
    const piece = document.createElement('div');
    const x = Math.random() * 100;
    const delay = Math.random() * .6;
    const duration = 1.5 + Math.random() * 2;
    const color = colors[Math.floor(Math.random() * colors.length)];
    piece.style.cssText = `
      position:absolute; top:-10px; left:${x}%;
      width:${6 + Math.random() * 6}px; height:${6 + Math.random() * 6}px;
      background:${color}; border-radius:${Math.random() > .5 ? '50%' : '2px'};
      animation: confettiFall ${duration}s ${delay}s ease-in forwards;
    `;
    container.appendChild(piece);
  }

  // Inject animation if not yet present
  if (!document.getElementById('confettiStyle')) {
    const style = document.createElement('style');
    style.id = 'confettiStyle';
    style.textContent = `
      @keyframes confettiFall {
        0%   { transform: translateY(0) rotate(0deg) scale(1); opacity: 1; }
        80%  { opacity: 1; }
        100% { transform: translateY(100vh) rotate(${Math.random() * 720}deg) scale(.3); opacity: 0; }
      }
    `;
    document.head.appendChild(style);
  }

  setTimeout(() => container.remove(), 4000);
}


// ── Alert Polling ────────────────────────────────────────────────
async function checkAlerts() {
  try {
    const res = await fetch('/api/alerts');
    const data = await res.json();

    const alertContainer = document.querySelector('.sidebar-alerts');
    if (!alertContainer) return;

    alertContainer.innerHTML = '';

    if (data.overdue.length > 0) {
      const a = document.createElement('a');
      a.href = '/?status=overdue';
      a.className = 'alert-badge overdue';
      a.innerHTML = `<i class="fas fa-exclamation-triangle"></i> <span>${data.overdue.length} Overdue</span>`;
      alertContainer.appendChild(a);
    }

    if (data.due_soon.length > 0) {
      const a = document.createElement('a');
      a.href = '/?status=due_soon';
      a.className = 'alert-badge due-soon';
      a.innerHTML = `<i class="fas fa-clock"></i> <span>${data.due_soon.length} Due Soon</span>`;
      alertContainer.appendChild(a);
    }
  } catch (e) {
    // Silently fail on network errors
  }
}


// ── Utility: Quick Status Change ─────────────────────────────────
async function changeStatus(toolId, newStatus) {
  try {
    const res = await fetch(`/api/tools/${toolId}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus })
    });
    if (res.ok) {
      location.reload();
    }
  } catch (e) {
    alert('Failed to update status.');
  }
}
