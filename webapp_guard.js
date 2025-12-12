const API_BASE = "https://api.firstgamble.ru";

let tgInitData = "";
let tg = null;

function isColorDark(hex){
  if(!hex || hex[0] !== "#") return false;
  const r = parseInt(hex.slice(1,3),16),
        g = parseInt(hex.slice(3,5),16),
        b = parseInt(hex.slice(5,7),16);
  return (0.299*r + 0.587*g + 0.114*b)/255 < 0.5;
}

/**
 * initTelegramGuard()
 * - если НЕ Telegram WebApp или нет initData -> редирект на /error_notg.html
 * - если всё ок -> настраивает тему, выставляет tgInitData и возвращает объект WebApp
 */
function initTelegramGuard(){
  const wa = window.Telegram && window.Telegram.WebApp;
  if(!wa){
    window.location.href = "/error_notg.html";
    return null;
  }

  wa.ready();
  tgInitData = wa.initData || "";

  if(!tgInitData){
    window.location.href = "/error_notg.html";
    return null;
  }

  if(!window.__tgExpanded){
    try { wa.expand(); } catch(e){}
    try { wa.disableVerticalSwipes(); } catch(e){}
    window.__tgExpanded = true;
  }

  document.documentElement.style.overscrollBehavior = "none";
  document.body.style.overscrollBehavior = "none";

  const p = wa.themeParams || {};
  if(p.bg_color) document.documentElement.style.setProperty("--bg", p.bg_color);
  if(p.secondary_bg_color) document.documentElement.style.setProperty("--panel", p.secondary_bg_color);
  if(p.text_color) document.documentElement.style.setProperty("--text", p.text_color);
  if(p.hint_color) document.documentElement.style.setProperty("--muted", p.hint_color);
  if(p.text_color){
    document.documentElement.setAttribute(
      "data-theme",
      isColorDark(p.text_color) ? "light" : "dark"
    );
  }
  try {
    if(p.bg_color){
      wa.setHeaderColor(p.bg_color);
      wa.setBackgroundColor(p.bg_color);
    }
  } catch(e){}

  tg = wa;
  return wa;
}

async function apiGet(path){
  const headers = {};
  if(tgInitData){
    headers["X-Telegram-InitData"] = tgInitData;
  }

  const res = await fetch(API_BASE + path, {
    method: "GET",
    headers,
    cache: "no-store",
  });

  if(res.status === 403){
      const data = await res.json().catch(()=>({}));
      if(data.detail && String(data.detail).startsWith('banned:')){
          throw new Error(data.detail);
      }
  }

  return await res.json();
}

async function apiPost(path, body){
  const headers = { "Content-Type": "application/json" };
  if(tgInitData){
    headers["X-Telegram-InitData"] = tgInitData;
  }

  const res = await fetch(API_BASE + path, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    cache: "no-store",
  });
  return await res.json();
}

async function fetchProfile(){
  try{
    const res = await apiGet("/api/profile");
    if(res && res.detail && typeof res.detail === 'string' && res.detail.startsWith('banned:')){
       const parts = res.detail.split('|');
       const reason = parts[0].replace('banned: ', '').trim();
       const until = parts[1] || '';
       window.location.href = `/banned.html?reason=${encodeURIComponent(reason)}&until=${encodeURIComponent(until)}`;
       return null;
    }
    return res;
  }catch(e){
    if(String(e).includes('banned:')){
        const msg = String(e);
        const parts = msg.split('|');
        const reason = parts[0].replace('Error: banned: ', '').replace('banned: ', '').trim();
        const until = parts[1] || '';
        window.location.href = `/banned.html?reason=${encodeURIComponent(reason)}&until=${encodeURIComponent(until)}`;
        return null;
    }
    return {ok:false, error:String(e)};
  }
}

async function ensureNicknameOrRedirect(uid){
  const profile = await fetchProfile();
  if(profile && profile.ok){
    const name = (profile.name || "").trim();
    if(!name){
      const query = uid ? `?uid=${uid}` : "";
      window.location.href = `/nickname${query}`;
      return null;
    }
  }
  return profile;
}
