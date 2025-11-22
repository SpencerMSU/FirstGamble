import { useEffect, useMemo, useState } from 'react';
import './styles/app.css';
import './styles/cards.css';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8080';

const GAME_TYPES = {
  dice: 'dice',
  blackjack: 'blackjack',
  slots: 'slots',
};

const initialCooldowns = {
  dice: 0,
  blackjack: 0,
  slots: 0,
};

function formatTime(seconds) {
  if (!seconds || seconds <= 0) return 'готово';
  const m = Math.floor(seconds / 60)
    .toString()
    .padStart(2, '0');
  const s = (seconds % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

function useThemeSync() {
  const [theme, setTheme] = useState('dark');

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    const detected = tg?.colorScheme || (prefersDark ? 'dark' : 'light');
    setTheme(detected);
    document.documentElement.setAttribute('data-theme', detected);

    const handleTheme = () => {
      const nextTheme = tg?.colorScheme || detected;
      setTheme(nextTheme);
      document.documentElement.setAttribute('data-theme', nextTheme);
    };
    tg?.onEvent?.('themeChanged', handleTheme);
    return () => tg?.offEvent?.('themeChanged', handleTheme);
  }, []);

  return theme;
}

function useInitData() {
  const [initData, setInitData] = useState('');
  const [manual, setManual] = useState('');

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (tg?.initData) {
      setInitData(tg.initData);
      tg.ready?.();
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const fromQuery = params.get('initData');
    if (fromQuery) {
      setInitData(fromQuery);
    }
  }, []);

  const allowManual = !initData;
  const applyManual = () => {
    if (manual.trim()) setInitData(manual.trim());
  };

  return { initData, manual, setManual, allowManual, applyManual };
}

async function requestWithAuth(path, initData, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
      'X-Telegram-Init-Data': initData,
    },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const error = new Error(data?.detail?.message || data?.detail || 'Ошибка запроса');
    error.status = res.status;
    error.detail = data?.detail;
    throw error;
  }
  return data;
}

function SectionCard({ title, children, actions }) {
  return (
    <div className="card">
      <div className="card__header">
        <h3>{title}</h3>
        {actions && <div className="card__actions">{actions}</div>}
      </div>
      <div className="card__body">{children}</div>
    </div>
  );
}

function BalanceBadge({ points }) {
  return (
    <div className="pill pill--accent" title="Ваши очки">
      <span>Очки</span>
      <strong>{points}</strong>
    </div>
  );
}

function CooldownBadge({ seconds }) {
  const ready = !seconds || seconds <= 0;
  return <span className={`pill ${ready ? 'pill--ready' : 'pill--cooldown'}`}>{ready ? 'Можно играть' : `КД: ${formatTime(seconds)}`}</span>;
}

function DiceGame({ onPlay, result, loading, cooldown }) {
  const [count, setCount] = useState(3);

  const handlePlay = () => {
    if (!loading) onPlay(count);
  };

  return (
    <SectionCard
      title="Кости"
      actions={
        <div className="card__actions-inline">
          <CooldownBadge seconds={cooldown} />
          <button className="btn" onClick={handlePlay} disabled={loading || cooldown > 0}>
            {loading ? 'Бросаю…' : 'Бросить кубики'}
          </button>
        </div>
      }
    >
      <div className="form-row">
        <label>
          Кол-во кубиков (1-5)
          <input
            type="number"
            min={1}
            max={5}
            value={count}
            onChange={(e) => setCount(Math.min(5, Math.max(1, Number(e.target.value))))}
          />
        </label>
      </div>
      {result && (
        <div className="dice-result">
          <div className="dice-column">
            <p>Вы</p>
            <div className="dice-strip">
              {result.player.values.map((v, idx) => (
                <span key={idx} className="die">
                  {v}
                </span>
              ))}
            </div>
            <strong className="score">{result.player.total}</strong>
          </div>
          <div className="dice-column">
            <p>Робот</p>
            <div className="dice-strip dice-strip--robot">
              {result.robot.values.map((v, idx) => (
                <span key={idx} className="die die--robot">
                  {v}
                </span>
              ))}
            </div>
            <strong className="score">{result.robot.total}</strong>
          </div>
          <div className={`outcome outcome--${result.outcome}`}>
            {result.outcome === 'win' && 'Победа! +1 очко'}
            {result.outcome === 'draw' && 'Ничья'}
            {result.outcome === 'lose' && 'Проигрыш'}
          </div>
        </div>
      )}
    </SectionCard>
  );
}

function Card({ card }) {
  const suit = card?.slice(-1);
  const rank = card?.slice(0, -1);
  const isRed = suit === '♥' || suit === '♦';
  return (
    <div className={`playing-card ${isRed ? 'playing-card--red' : ''}`}>
      <span>{rank}</span>
      <span className="suit">{suit}</span>
    </div>
  );
}

function Blackjack({ onPlay, result, loading, cooldown }) {
  return (
    <SectionCard
      title="Блэкджек"
      actions={
        <div className="card__actions-inline">
          <CooldownBadge seconds={cooldown} />
          <button className="btn" onClick={onPlay} disabled={loading || cooldown > 0}>
            {loading ? 'Раздаю…' : 'Сыграть'}
          </button>
        </div>
      }
    >
      <p className="muted">Одна колода, дилер тянет до 17. Ничья в пользу дилера.</p>
      {result && (
        <div className="blackjack-grid">
          <div>
            <p>Ваши карты ({result.player_score})</p>
            <div className="card-row">
              {result.player_hand.map((c, idx) => (
                <Card card={c} key={idx} />
              ))}
            </div>
          </div>
          <div>
            <p>Дилер ({result.dealer_score})</p>
            <div className="card-row">
              {result.dealer_hand.map((c, idx) => (
                <Card card={c} key={idx} />
              ))}
            </div>
          </div>
        </div>
      )}
      {result && <div className={`outcome outcome--${result.outcome}`}>{result.outcome === 'win' ? 'Победа! +1 очко' : 'Дилер победил'}</div>}
    </SectionCard>
  );
}

function Slots({ onPlay, result, loading, cooldown, spinning }) {
  const symbols = result?.reels || ['🍒', '🔔', '⭐'];
  return (
    <SectionCard
      title="Слотики"
      actions={
        <div className="card__actions-inline">
          <CooldownBadge seconds={cooldown} />
          <button className="btn btn--danger" onClick={onPlay} disabled={loading || cooldown > 0}>
            {loading ? 'Кручусь…' : 'Играть'}
          </button>
        </div>
      }
    >
      <div className={`slot-machine ${spinning ? 'slot-machine--spin' : ''}`}>
        {symbols.map((symbol, idx) => (
          <div key={idx} className="slot-reel">
            <div className="slot-window">{symbol}</div>
            <div className="slot-blur">{symbol}</div>
          </div>
        ))}
      </div>
      {result && <div className={`outcome outcome--${result.outcome}`}>{result.outcome === 'win' ? 'Джекпот! +1 очко' : 'Попробуй ещё'}</div>}
    </SectionCard>
  );
}

function Shop({ balance, items, onRefresh }) {
  return (
    <SectionCard
      title="Магазин"
      actions={<button className="btn btn--ghost" onClick={onRefresh}>Обновить</button>}
    >
      <div className="shop-balance">
        <BalanceBadge points={balance} />
      </div>
      <div className="shop-list">
        {items.map((item, idx) => (
          <div key={idx} className="shop-item">
            <div>
              <h4>{item.title}</h4>
              <p className="muted">{item.description}</p>
            </div>
            <span className="pill pill--accent">{item.price_points} очков</span>
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

function Leaderboard({ top, me, onRefresh }) {
  return (
    <SectionCard
      title="Рейтинг"
      actions={<button className="btn btn--ghost" onClick={onRefresh}>Обновить</button>}
    >
      <div className="leaderboard">
        {top.map((user) => (
          <div key={user.tg_id} className={`leader-row ${me?.tg_id === user.tg_id ? 'leader-row--me' : ''}`}>
            <span className="rank">#{user.rank}</span>
            <span className="username">{user.username || `id${user.tg_id}`}</span>
            <span className="points">{user.points} очков</span>
          </div>
        ))}
      </div>
      {me && (
        <div className="leader-me">
          <p>Ваша позиция</p>
          <div className="leader-row leader-row--me">
            <span className="rank">#{me.rank}</span>
            <span className="username">{me.username || `id${me.tg_id}`}</span>
            <span className="points">{me.points} очков</span>
          </div>
        </div>
      )}
    </SectionCard>
  );
}

function Placeholder({ title, children }) {
  return (
    <SectionCard title={title}>
      <p className="muted">{children}</p>
    </SectionCard>
  );
}

export default function App() {
  const theme = useThemeSync();
  const { initData, manual, setManual, allowManual, applyManual } = useInitData();
  const [profile, setProfile] = useState(null);
  const [cooldowns, setCooldowns] = useState(initialCooldowns);
  const [shop, setShop] = useState({ balance: 0, items: [] });
  const [leaderboardData, setLeaderboardData] = useState({ top: [], me: null });
  const [results, setResults] = useState({ dice: null, blackjack: null, slots: null });
  const [spinning, setSpinning] = useState(false);
  const [loadingGame, setLoadingGame] = useState({ dice: false, blackjack: false, slots: false });
  const [section, setSection] = useState('ludka');
  const [gameTab, setGameTab] = useState(GAME_TYPES.dice);
  const [error, setError] = useState('');
  const [authError, setAuthError] = useState('');

  const readyForApi = useMemo(() => Boolean(initData), [initData]);

  useEffect(() => {
    if (!readyForApi) return;

    const bootstrap = async () => {
      try {
        setAuthError('');
        const profileData = await requestWithAuth('/auth/telegram', initData, {
          method: 'POST',
          body: JSON.stringify({ init_data: initData }),
        });
        setProfile(profileData);
        await Promise.all([fetchCooldowns(initData), fetchShop(initData), fetchLeaderboard(initData)]);
      } catch (e) {
        setAuthError(e.message || 'Не удалось авторизоваться через Telegram');
      }
    };
    bootstrap();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readyForApi]);

  useEffect(() => {
    const interval = setInterval(() => {
      setCooldowns((prev) => {
        const next = { ...prev };
        Object.keys(next).forEach((key) => {
          if (next[key] > 0) next[key] -= 1;
        });
        return next;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const fetchCooldowns = async (data = initData) => {
    try {
      const resp = await requestWithAuth('/cooldowns', data, { method: 'GET' });
      const mapped = { ...initialCooldowns };
      resp.cooldowns.forEach((cd) => {
        mapped[cd.game_type] = cd.remaining_seconds;
      });
      setCooldowns(mapped);
    } catch (e) {
      setError(e.message);
    }
  };

  const fetchShop = async (data = initData) => {
    try {
      const resp = await requestWithAuth('/shop', data, { method: 'GET' });
      setShop(resp);
      setProfile((prev) => (prev ? { ...prev, points: resp.balance } : prev));
    } catch (e) {
      setError(e.message);
    }
  };

  const fetchLeaderboard = async (data = initData) => {
    try {
      const resp = await requestWithAuth('/leaderboard', data, { method: 'GET' });
      setLeaderboardData(resp);
    } catch (e) {
      setError(e.message);
    }
  };

  const updateFromOutcome = (outcome, pointsAwarded) => {
    if (pointsAwarded) {
      setProfile((prev) => (prev ? { ...prev, points: prev.points + pointsAwarded } : prev));
    }
  };

  const handleDice = async (diceCount) => {
    setLoadingGame((prev) => ({ ...prev, dice: true }));
    setError('');
    try {
      const resp = await requestWithAuth('/game/dice', initData, {
        method: 'POST',
        body: JSON.stringify({ dice_count: diceCount }),
      });
      setResults((prev) => ({ ...prev, dice: resp }));
      updateFromOutcome(resp.outcome, resp.points_awarded);
      await fetchCooldowns();
    } catch (e) {
      setError(e.message);
      if (e.status === 429 && e.detail?.remaining_seconds) {
        setCooldowns((prev) => ({ ...prev, dice: e.detail.remaining_seconds }));
      }
    } finally {
      setLoadingGame((prev) => ({ ...prev, dice: false }));
    }
  };

  const handleBlackjack = async () => {
    setLoadingGame((prev) => ({ ...prev, blackjack: true }));
    setError('');
    try {
      const resp = await requestWithAuth('/game/blackjack', initData, { method: 'POST' });
      setResults((prev) => ({ ...prev, blackjack: resp }));
      updateFromOutcome(resp.outcome, resp.points_awarded);
      await fetchCooldowns();
    } catch (e) {
      setError(e.message);
      if (e.status === 429 && e.detail?.remaining_seconds) {
        setCooldowns((prev) => ({ ...prev, blackjack: e.detail.remaining_seconds }));
      }
    } finally {
      setLoadingGame((prev) => ({ ...prev, blackjack: false }));
    }
  };

  const handleSlots = async () => {
    setLoadingGame((prev) => ({ ...prev, slots: true }));
    setSpinning(true);
    setError('');
    try {
      const resp = await requestWithAuth('/game/slots', initData, { method: 'POST' });
      setResults((prev) => ({ ...prev, slots: resp }));
      updateFromOutcome(resp.outcome, resp.points_awarded);
      await fetchCooldowns();
    } catch (e) {
      setError(e.message);
      if (e.status === 429 && e.detail?.remaining_seconds) {
        setCooldowns((prev) => ({ ...prev, slots: e.detail.remaining_seconds }));
      }
    } finally {
      setTimeout(() => setSpinning(false), 500);
      setLoadingGame((prev) => ({ ...prev, slots: false }));
    }
  };

  const renderLudka = () => (
    <div className="panel">
      <div className="tabs">
        <button className={gameTab === GAME_TYPES.dice ? 'tab tab--active' : 'tab'} onClick={() => setGameTab(GAME_TYPES.dice)}>
          Кости
        </button>
        <button
          className={gameTab === GAME_TYPES.blackjack ? 'tab tab--active' : 'tab'}
          onClick={() => setGameTab(GAME_TYPES.blackjack)}
        >
          Блэкджек
        </button>
        <button className={gameTab === GAME_TYPES.slots ? 'tab tab--active' : 'tab'} onClick={() => setGameTab(GAME_TYPES.slots)}>
          Слотики
        </button>
        <button className={gameTab === 'leaderboard' ? 'tab tab--active' : 'tab'} onClick={() => setGameTab('leaderboard')}>
          Рейтинг
        </button>
      </div>
      {gameTab === GAME_TYPES.dice && (
        <DiceGame
          onPlay={handleDice}
          result={results.dice}
          loading={loadingGame.dice}
          cooldown={cooldowns.dice}
        />
      )}
      {gameTab === GAME_TYPES.blackjack && (
        <Blackjack
          onPlay={handleBlackjack}
          result={results.blackjack}
          loading={loadingGame.blackjack}
          cooldown={cooldowns.blackjack}
        />
      )}
      {gameTab === GAME_TYPES.slots && (
        <Slots
          onPlay={handleSlots}
          result={results.slots}
          loading={loadingGame.slots}
          cooldown={cooldowns.slots}
          spinning={spinning}
        />
      )}
      {gameTab === 'leaderboard' && (
        <Leaderboard top={leaderboardData.top} me={leaderboardData.me} onRefresh={() => fetchLeaderboard()} />
      )}
    </div>
  );

  const renderSection = () => {
    switch (section) {
      case 'ludka':
        return renderLudka();
      case 'shop':
        return <Shop balance={shop.balance} items={shop.items} onRefresh={() => fetchShop()} />;
      case 'prices':
        return (
          <Placeholder title="Цены и очки">
            Зарабатывайте очки победами в играх. Кости/Блэкджек/Слотики дают +1 очко за победу. Очки копятся и тратятся в магазине.
          </Placeholder>
        );
      case 'rpg':
        return <Placeholder title="RPG">Раздел для будущих режимов RPG. Сейчас доступна аркада «Лудка».</Placeholder>;
      case 'draws':
        return <Placeholder title="Розыгрыши">Скоро появятся розыгрыши и спец-акции. Следите за обновлениями.</Placeholder>;
      default:
        return null;
    }
  };

  if (!readyForApi) {
    return (
      <main className="container">
        <div className="card">
          <h2>Откройте через Telegram Mini App</h2>
          <p className="muted">
            Мы не увидели initData от Telegram. Запустите бот, нажмите «Подтвердить» и откройте мини-приложение. Для локальной проверки вставьте
            initData вручную.
          </p>
          {allowManual && (
            <div className="form-row">
              <label>
                initData
                <textarea value={manual} onChange={(e) => setManual(e.target.value)} placeholder="скопируйте строку initData сюда" />
              </label>
              <button className="btn" onClick={applyManual} disabled={!manual.trim()}>
                Применить initData
              </button>
            </div>
          )}
        </div>
      </main>
    );
  }

  return (
    <main className="container">
      <header className="topbar">
        <div>
          <p className="eyebrow">FirstGamble</p>
          <h1>Мини-приложение</h1>
          {profile && (
            <p className="muted">
              {profile.first_name || profile.username || 'Игрок'} • tgId {profile.tg_id}
            </p>
          )}
        </div>
        <div className="topbar__stats">
          <span className="pill">Тема: {theme === 'dark' ? 'тёмная' : 'светлая'}</span>
          <BalanceBadge points={profile?.points || 0} />
        </div>
      </header>

      <nav className="nav">
        {[
          { id: 'ludka', label: 'Лудка' },
          { id: 'prices', label: 'Цены' },
          { id: 'rpg', label: 'RPG' },
          { id: 'shop', label: 'Магазин' },
          { id: 'draws', label: 'Розыгрыши' },
        ].map((item) => (
          <button key={item.id} className={section === item.id ? 'nav__btn nav__btn--active' : 'nav__btn'} onClick={() => setSection(item.id)}>
            {item.label}
          </button>
        ))}
      </nav>

      {authError && <div className="alert alert--error">{authError}</div>}
      {error && <div className="alert">{error}</div>}

      {renderSection()}
    </main>
  );
}
