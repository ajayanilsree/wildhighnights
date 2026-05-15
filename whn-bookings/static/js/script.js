'use strict';

// ========================
// CONSTANTS
// ========================
let ARTISTS = []; // Will be fetched from Django

const STATUS = { confirmed: 'Confirmed', tentative: 'Tentative', cancelled: 'Cancelled' };

const EVENT_TYPES = {
  gig:      { label: 'Gig',        icon: '🎧', color: null       }, 
  shoot:    { label: 'Shoot Day',  icon: '📸', color: '#5856D6'  },
  vacation: { label: 'Vacation',   icon: '🏖️', color: '#00C7BE'  },
  travel:   { label: 'Travel',     icon: '✈️', color: '#FF6B00'  },
  other:    { label: 'Other',      icon: '📌', color: '#8E8E93'  },
};

// ========================
// AUTH HELPERS
// ========================
const AUTH = {
  get() { 
    // We'll rely on Django session cookies, but we might store basic user info here
    try { return JSON.parse(localStorage.getItem('whn_user') || 'null'); } catch { return null; }
  },
  set(user) { localStorage.setItem('whn_user', JSON.stringify(user)); },
  clear() { localStorage.removeItem('whn_user'); },
  isLoggedIn() { return !!this.get(); }
};

// ========================
// DATABASE (Django API)
// ========================
const DB = {
  _data: [],

  async syncArtists() {
    try {
        const r = await fetch('/api/artists/');
        if (r.ok) {
            ARTISTS = await r.json();
        }
    } catch (e) {
        console.error('Fetch artists failed:', e);
    }
  },

  async sync() {
    try {
      const r = await fetch('/api/bookings/');
      if (r.ok) {
        this._data = await r.json();
      }
    } catch (e) {
      console.error('Sync bookings failed:', e);
    }
  },

  get() { return [...this._data]; },
  forArtist(id) { return this._data.filter(e => e.artistId === id); },
  forDate(id, date) { return this._data.filter(e => e.artistId === id && e.date === date); },
  forMonth(id, year, month) {
    return this._data.filter(e => {
      if (e.artistId !== id) return false;
      const d = parseDate(e.date);
      return d.getFullYear() === year && d.getMonth() === month;
    });
  },

  async add(event) {
    const r = await fetch('/api/bookings/', {
      method: 'POST',
      headers: { 
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken')
      },
      body: JSON.stringify(event),
    });
    if (r.ok) {
        const newEv = await r.json();
        this._data.push(newEv);
        return newEv;
    }
  },

  async update(id, patch) {
    const r = await fetch(`/api/bookings/${id}/`, {
      method: 'PATCH',
      headers: { 
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken')
      },
      body: JSON.stringify(patch),
    });
    if (r.ok) {
        const updated = await r.json();
        const i = this._data.findIndex(e => e.id === id);
        if (i >= 0) this._data[i] = updated;
    }
  },

  async remove(id) {
    const r = await fetch(`/api/bookings/${id}/`, {
      method: 'DELETE',
      headers: { 'X-CSRFToken': getCookie('csrftoken') }
    });
    if (r.ok) {
        this._data = this._data.filter(e => e.id !== id);
    }
  },
};

// ========================
// DATE HELPERS
// ========================
function toDateStr(d) {
  return d.getFullYear() + '-' + pad(d.getMonth()+1) + '-' + pad(d.getDate());
}
function pad(n) { return String(n).padStart(2, '0'); }
function parseDate(s) {
  const [y,m,d] = s.split('-').map(Number);
  return new Date(y, m-1, d);
}
function displayDate(s) {
  return parseDate(s).toLocaleDateString('en-IN', { weekday:'short', day:'numeric', month:'long', year:'numeric' });
}
function monthYearLabel(y, m) {
  return new Date(y, m, 1).toLocaleDateString('en-IN', { month:'long', year:'numeric' });
}
function inr(n) { return n ? '₹' + Number(n).toLocaleString('en-IN') : '—'; }
const TODAY = toDateStr(new Date());

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// ========================
// APP STATE
// ========================
let state = {
  route: '',
  artistId: '',
  selDate: TODAY,
  calYear: new Date().getFullYear(),
  calMonth: new Date().getMonth(),
  adminArtist: 'all',
  adminStatus: 'all',
};

// ========================
// ROUTER
// ========================
function getRoute() { return location.hash.slice(1) || '/'; }
function go(path) { location.hash = path; }

async function handleRoute() {
  const route = getRoute();
  state.route = route;
  closeSheet();
  closeModal();

  // If we are on a dedicated Django page (not the root /), 
  // disable the JS router logic to prevent interference.
  if (window.location.pathname !== '/') return;

  if (route === '/' || route === '' || route === '/login') {
    // Let Django handle the premium homepage content
    if (route === '/' || route === '') {
        // If we are coming from a mounted JS view (like artist detail), 
        // we might need to reload to get the Django-rendered homepage back.
        if (!document.getElementById('events') && !document.getElementById('login-card')) {
            window.location.href = '/'; 
        }
    }
    return;
  }

  if (route.startsWith('/a/')) {
    const id = route.split('/')[2];
    state.artistId = id;
    renderCalendar();
    return;
  }

  if (route === '/admin') {
    renderAdminDashboard();
    return;
  }
}

window.addEventListener('hashchange', async () => {
  await DB.sync();
  handleRoute();
});

window.addEventListener('load', async () => {
    // We now use the HTML-based loader in base.html
    await DB.syncArtists();
    await DB.sync();
    handleRoute();
});

// renderLanding is now handled by Django index.html

// ========================
// CALENDAR VIEW
// ========================
function renderCalendar() {
  const artist = ARTISTS.find(a => a.id === state.artistId);
  if (!artist) return go('/');

  const { calYear: y, calMonth: m, selDate } = state;
  const monthGigs = DB.forMonth(artist.id, y, m);

  const gigMap = {};
  monthGigs.forEach(g => { (gigMap[g.date] = gigMap[g.date] || []).push(g); });

  const firstDay = new Date(y, m, 1).getDay();
  const daysInMonth = new Date(y, m+1, 0).getDate();
  const prevDays = new Date(y, m, 0).getDate();

  let cells = [];
  for (let i = firstDay-1; i >= 0; i--)
    cells.push({ n: prevDays-i, date: toDateStr(new Date(y,m-1,prevDays-i)), cur: false });
  for (let d = 1; d <= daysInMonth; d++)
    cells.push({ n: d, date: toDateStr(new Date(y,m,d)), cur: true });
  while (cells.length < 42) {
    const d = cells.length - firstDay - daysInMonth + 1;
    cells.push({ n: d, date: toDateStr(new Date(y,m+1,d)), cur: false });
  }

  const calHTML = cells.map(c => {
    const events = gigMap[c.date] || [];
    const isToday = c.date === TODAY;
    const isSel = c.date === selDate && !isToday;
    const dots = events.slice(0,3).map(e => `<div class="gig-dot ${dotClass(e)}"></div>`).join('');
    let cls = 'cal-day' + (!c.cur ? ' other-month' : '') + (isToday ? ' today' : '') + (isSel ? ' selected' : '');
    return `<div class="${cls}" data-date="${c.date}"><div class="cal-day-num">${c.n}</div><div class="gig-dots">${dots}</div></div>`;
  }).join('');

  const gigListHTML = buildPublicGigList(artist.id, selDate);

  const upcoming = DB.forArtist(artist.id)
    .filter(e => e.date >= TODAY && e.status !== 'cancelled')
    .sort((a,b) => a.date.localeCompare(b.date))
    .slice(0, 5);

  const upcomingHTML = upcoming.length ? `
    <div class="upcoming-section">
      <div class="section-label" style="padding-bottom:4px">Upcoming</div>
      ${upcoming.map(e => eventCardHTML(e, true)).join('')}
    </div>
  ` : '';

  mount(`
    <div class="calendar-view page-enter" style="--artist-color:${artist.color}">
      <div class="nav-bar">
        <div class="nav-bar-inner">
          <button class="nav-btn" onclick="go('/')">‹ Back</button>
          <span class="nav-title" style="color:${artist.color}">${artist.emoji} ${artist.name}</span>
          <div style="min-width:60px"></div>
        </div>
      </div>

      <div class="month-nav">
        <button class="month-nav-btn" id="prevM">‹</button>
        <div class="month-nav-title">${monthYearLabel(y, m)}</div>
        <button class="month-nav-btn" id="nextM">›</button>
      </div>

      <div class="weekday-header">
        ${['S','M','T','W','T','F','S'].map(d=>`<div class="weekday-label">${d}</div>`).join('')}
      </div>

      <div class="calendar-grid" id="calGrid">${calHTML}</div>

      <div class="gig-list-section" id="gigList">
        <div class="section-label">${displayDate(selDate)}</div>
        ${gigListHTML}
      </div>

      ${upcomingHTML}
    </div>
  `);

  attachCalEvents(artist.id);
}

function dotClass(e) {
  const et = e.eventType || 'gig';
  if (et === 'gig') return e.status || 'confirmed';
  return et;
}

function eventBarColor(e) {
  const et = e.eventType || 'gig';
  if (et === 'gig') return `var(--status-${e.status || 'confirmed'})`;
  return EVENT_TYPES[et]?.color || '#8E8E93';
}

function eventTitle(e) {
  const et = e.eventType || 'gig';
  if (et === 'gig') return e.venue || '—';
  return e.title || EVENT_TYPES[et]?.label || 'Event';
}

function eventCardHTML(e, showDate = false) {
  const et = e.eventType || 'gig';
  const isGig = et === 'gig';
  const etInfo = EVENT_TYPES[et] || EVENT_TYPES.other;

  const badge = isGig
    ? `<div class="status-badge ${e.status}">${STATUS[e.status] || ''}</div>`
    : `<div class="event-type-badge" style="background:${etInfo.color}18;color:${etInfo.color}">${etInfo.icon} ${etInfo.label}</div>`;

  const meta = [];
  if (showDate) meta.push(`<span>📅 ${displayDate(e.date)}</span>`);
  if (isGig && e.city) meta.push(`<span>📍 ${e.city}</span>`);
  if (!isGig && e.city) meta.push(`<span>📍 ${e.city}</span>`);
  if (e.startTime) meta.push(`<span>🕙 ${e.startTime}${e.endTime?'–'+e.endTime:''}</span>`);

  const note = e.publicNotes || e.description || '';

  return `
    <button class="gig-card" data-gig="${e.id}">
      <div class="gig-status-bar" style="background:${eventBarColor(e)}"></div>
      <div class="gig-card-body">
        <div class="gig-venue">${etInfo.icon} ${eventTitle(e)}</div>
        ${meta.length ? `<div class="gig-meta">${meta.join('')}</div>` : ''}
        ${note ? `<div style="font-size:12px;color:var(--text-secondary);margin-top:4px">${note}</div>` : ''}
      </div>
      ${badge}
    </button>
  `;
}

function buildPublicGigList(artistId, date) {
  const events = DB.forDate(artistId, date);
  if (!events.length) return `<div class="no-gigs"><div class="no-gigs-icon">📅</div>Nothing scheduled for today</div>`;
  return events.map(e => eventCardHTML(e)).join('');
}

function attachCalEvents(artistId) {
  document.getElementById('prevM')?.addEventListener('click', () => {
    state.calMonth--;
    if (state.calMonth < 0) { state.calMonth = 11; state.calYear--; }
    renderCalendar();
  });
  document.getElementById('nextM')?.addEventListener('click', () => {
    state.calMonth++;
    if (state.calMonth > 11) { state.calMonth = 0; state.calYear++; }
    renderCalendar();
  });

  document.querySelectorAll('.cal-day:not(.other-month)').forEach(el => {
    el.addEventListener('click', () => {
      const date = el.dataset.date;
      state.selDate = date;

      document.querySelectorAll('.cal-day').forEach(d => d.classList.remove('selected'));
      if (el.dataset.date !== TODAY) el.classList.add('selected');
      else el.classList.add('today');

      const list = document.getElementById('gigList');
      list.innerHTML = `<div class="section-label">${displayDate(date)}</div>${buildPublicGigList(artistId, date)}`;
      attachGigCardClicks(artistId, false);
      list.scrollIntoView({ behavior:'smooth', block:'nearest' });
    });
  });

  attachGigCardClicks(artistId, false);
}

function attachGigCardClicks(artistId, isAdmin) {
  document.querySelectorAll('.gig-card[data-gig]').forEach(card => {
    card.addEventListener('click', () => {
      const ev = DB.get().find(g => g.id == card.dataset.gig);
      if (ev) showEventSheet(ev, isAdmin, artistId);
    });
  });
}

// ========================
// BOTTOM SHEET — EVENT DETAIL
// ========================
function showEventSheet(ev, isAdmin = false, artistId = '') {
  const et = ev.eventType || 'gig';
  const isGig = et === 'gig';
  const etInfo = EVENT_TYPES[et] || EVENT_TYPES.other;

  const rows = [];
  if (isGig && ev.city) rows.push(`<div class="detail-row"><div class="detail-icon">📍</div><div><div class="detail-label">City</div><div class="detail-value">${ev.city}</div></div></div>`);
  if (!isGig && ev.city) rows.push(`<div class="detail-row"><div class="detail-icon">📍</div><div><div class="detail-label">Location</div><div class="detail-value">${ev.city}</div></div></div>`);
  if (ev.startTime) rows.push(`<div class="detail-row"><div class="detail-icon">🕙</div><div><div class="detail-label">${isGig?'Set Time':'Time'}</div><div class="detail-value">${ev.startTime}${ev.endTime?' – '+ev.endTime:''}</div></div></div>`);
  if (isGig) rows.push(`<div class="detail-row"><div class="detail-icon">✅</div><div><div class="detail-label">Status</div><div class="detail-value"><span class="status-badge ${ev.status}">${STATUS[ev.status]||''}</span></div></div></div>`);
  
  const note = ev.publicNotes || ev.description || '';
  if (note) rows.push(`<div class="detail-row"><div class="detail-icon">📝</div><div><div class="detail-label">Notes</div><div class="detail-value">${note}</div></div></div>`);

  const overlay = el('div', 'overlay');
  overlay.addEventListener('click', closeSheet);

  const sheet = el('div', 'bottom-sheet');
  sheet.innerHTML = `
    <div class="sheet-handle"></div>
    <div class="sheet-header">
      <div class="sheet-date-label">${displayDate(ev.date)}</div>
      <div class="sheet-venue-name">${etInfo.icon} ${eventTitle(ev)}</div>
    </div>
    <div class="sheet-body">${rows.join('')}</div>
    <div style="height:8px"></div>
  `;

  document.body.appendChild(overlay);
  document.body.appendChild(sheet);
  requestAnimationFrame(() => { overlay.classList.add('active'); sheet.classList.add('active'); });
}

function closeSheet() {
  document.querySelectorAll('.overlay, .bottom-sheet').forEach(e => {
    e.classList.remove('active');
    setTimeout(() => e.remove(), 340);
  });
}

function closeModal() {
  const ov = document.querySelector('.modal-overlay');
  if (!ov) return;
  ov.classList.remove('active');
  setTimeout(() => ov.remove(), 340);
}

// ========================
// UTILS
// ========================
function mount(html) {
  document.getElementById('app').innerHTML = html;
}

function el(tag, cls) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  return e;
}

window.go = go;
