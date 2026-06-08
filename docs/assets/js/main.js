/* ============================================
   SQL-IQ Leaderboard - Main JavaScript
   ============================================ */

// --- State ---
let leaderboardData = [];
let currentSort = { key: 'overall', direction: 'desc' };
let currentFilter = 'all';

// --- Task Definitions ---
const TASKS = [
  { key: 'text2sql', label: 'Text2SQL', dimension: 'generation' },
  { key: 'conversational_sql', label: 'Conv SQL', dimension: 'generation' },
  { key: 'sql_judge', label: 'SQL Judge', dimension: 'comprehension' },
  { key: 'sql_equ_judge', label: 'Equ Judge', dimension: 'comprehension' },
  { key: 'sql_err_class', label: 'Err Class', dimension: 'debugging' },
  { key: 'sql_debugging', label: 'SQL Correction', dimension: 'debugging' },
  { key: 'sql_trans', label: 'SQL Trans', dimension: 'adaptation' }
];

const DIMENSION_MAP = {
  all: TASKS.map(t => t.key),
  generation: ['text2sql', 'conversational_sql'],
  comprehension: ['sql_judge', 'sql_equ_judge'],
  debugging: ['sql_err_class', 'sql_debugging'],
  adaptation: ['sql_trans']
};

// --- Initialize ---
document.addEventListener('DOMContentLoaded', async () => {
  await loadData();
  renderTable();
  renderStats();
  renderTranslationTable();
  bindEvents();
});

// --- Data Loading ---
async function loadData() {
  try {
    const response = await fetch('data/leaderboard.json');
    if (!response.ok) throw new Error('Failed to load data');
    leaderboardData = await response.json();
  } catch (error) {
    console.error('Error loading leaderboard data:', error);
    leaderboardData = [];
  }
}

// --- Compute Overall ---
// When filter is "all", use the pre-computed overall from data (paper's Avg);
// otherwise average visible tasks.
function computeOverall(entry, taskKeys) {
  const keys = taskKeys || DIMENSION_MAP[currentFilter];
  // Use pre-computed overall when showing all tasks
  if (currentFilter === 'all' && entry.overall !== null && entry.overall !== undefined) {
    return entry.overall;
  }
  const values = keys
    .map(k => entry.scores[k])
    .filter(v => v !== null && v !== undefined);
  if (values.length === 0) return null;
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

// --- Sorting ---
function sortData(data) {
  const { key, direction } = currentSort;
  const visibleKeys = DIMENSION_MAP[currentFilter];

  return [...data].sort((a, b) => {
    let valA, valB;

    if (key === 'overall') {
      valA = computeOverall(a, visibleKeys);
      valB = computeOverall(b, visibleKeys);
    } else if (key === 'model' || key === 'organization') {
      valA = (a[key] || '').toLowerCase();
      valB = (b[key] || '').toLowerCase();
      if (direction === 'asc') return valA < valB ? -1 : valA > valB ? 1 : 0;
      return valA > valB ? -1 : valA < valB ? 1 : 0;
    } else {
      valA = a.scores[key];
      valB = b.scores[key];
    }

    // null values always go to the bottom regardless of sort direction
    if (valA === null || valA === undefined) return 1;
    if (valB === null || valB === undefined) return -1;

    return direction === 'desc' ? valB - valA : valA - valB;
  });
}

// --- Find best scores per column ---
function findBestScores(data, visibleKeys) {
  const best = {};
  visibleKeys.forEach(key => {
    const values = data
      .map(d => d.scores[key])
      .filter(v => v !== null && v !== undefined);
    best[key] = values.length > 0 ? Math.max(...values) : null;
  });

  const overalls = data
    .map(d => computeOverall(d, visibleKeys))
    .filter(v => v !== null && v !== undefined);
  best.overall = overalls.length > 0 ? Math.max(...overalls) : null;

  return best;
}

// --- Stats Rendering ---
function renderStats() {
  const statsEl = document.getElementById('leaderboard-stats');
  if (!statsEl) return;

  const totalModels = leaderboardData.length;
  const totalTasks = TASKS.length;
  const fullSubmissions = leaderboardData.filter(d =>
    TASKS.every(t => d.scores[t.key] !== null && d.scores[t.key] !== undefined)
  ).length;

  statsEl.textContent = `${totalModels} models · ${totalTasks} tasks · ${fullSubmissions} full submissions`;
}

// --- Table Rendering ---
function renderTable() {
  const tableContainer = document.getElementById('leaderboard-table');
  if (!tableContainer) return;

  const visibleKeys = DIMENSION_MAP[currentFilter];
  const visibleTasks = TASKS.filter(t => visibleKeys.includes(t.key));
  const sorted = sortData(leaderboardData);
  const bestScores = findBestScores(sorted, visibleKeys);

  // Empty state
  if (sorted.length === 0) {
    tableContainer.innerHTML = `
      <tbody>
        <tr>
          <td colspan="100%" class="text-center py-16 text-gray-400 text-sm">
            No data available yet.
          </td>
        </tr>
      </tbody>`;
    return;
  }

  // Overall column label changes based on filter
  const overallLabel = currentFilter === 'all' ? 'Avg' : `Avg (${capitalize(currentFilter)})`;

  // Build header
  let headerHTML = `
    <thead>
      <tr>
        <th class="rank-cell">#</th>
        <th data-sort="model" class="${getSortClass('model')}">Model</th>
        ${/* <th data-sort="organization" class="${getSortClass('organization')}">Organization</th> */ ''}
        <th data-sort="overall" class="${getSortClass('overall')}">${overallLabel}</th>`;

  visibleTasks.forEach(task => {
    headerHTML += `<th data-sort="${task.key}" class="${getSortClass(task.key)}">${task.label}</th>`;
  });

  headerHTML += `</tr></thead>`;

  // Build body
  let bodyHTML = '<tbody>';
  sorted.forEach((entry, index) => {
    const rank = index + 1;
    const rankClass = rank <= 3 ? `rank-${rank}` : '';
    const overall = computeOverall(entry, visibleKeys);

    const overallIsBest = overall !== null &&
      bestScores.overall !== null &&
      Math.abs(overall - bestScores.overall) < 0.01;

    bodyHTML += `<tr>
      <td class="rank-cell ${rankClass}">${rank}</td>
      <td class="model-cell">${escapeHTML(entry.model)}</td>
      ${/* <td>${escapeHTML(entry.organization || '—')}</td> */ ''}
      <td class="score-cell overall-cell ${overallIsBest ? 'score-best' : ''}">
        ${overall !== null ? overall.toFixed(1) : '<span class="score-na">—</span>'}
      </td>`;

    visibleTasks.forEach(task => {
      const score = entry.scores[task.key];
      const isBest = score !== null && score !== undefined &&
                     bestScores[task.key] !== null &&
                     Math.abs(score - bestScores[task.key]) < 0.01;
      bodyHTML += `<td class="score-cell ${isBest ? 'score-best' : ''}">
        ${score !== null && score !== undefined ? score.toFixed(1) : '<span class="score-na">—</span>'}
      </td>`;
    });

    bodyHTML += '</tr>';
  });
  bodyHTML += '</tbody>';

  tableContainer.innerHTML = headerHTML + bodyHTML;
}

// --- Helpers ---
function getSortClass(key) {
  if (currentSort.key !== key) return '';
  return currentSort.direction === 'asc' ? 'sorted-asc' : 'sorted-desc';
}

function capitalize(str) {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

function escapeHTML(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// --- Translation Breakdown ---
const TRANSLATION_DIALECTS = [
  { key: 'postgresql', label: 'PostgreSQL' },
  { key: 'mssql', label: 'MSSQL' },
  { key: 'oracle', label: 'Oracle' },
  { key: 'clickhouse', label: 'ClickHouse' },
  { key: 'druid', label: 'Druid' }
];

let translationSort = { key: 'avg', direction: 'desc' };

function renderTranslationTable() {
  const tableContainer = document.getElementById('translation-table');
  if (!tableContainer) return;

  // Sort data
  const sorted = [...leaderboardData].sort((a, b) => {
    const { key, direction } = translationSort;

    if (key === 'model' || key === 'organization') {
      const valA = (a[key] || '').toLowerCase();
      const valB = (b[key] || '').toLowerCase();
      if (direction === 'asc') return valA < valB ? -1 : valA > valB ? 1 : 0;
      return valA > valB ? -1 : valA < valB ? 1 : 0;
    }

    let valA, valB;
    if (key === 'avg') {
      valA = a.scores.sql_trans;
      valB = b.scores.sql_trans;
    } else {
      valA = a.translation_details ? a.translation_details[key] : null;
      valB = b.translation_details ? b.translation_details[key] : null;
    }

    if (valA === null || valA === undefined) return 1;
    if (valB === null || valB === undefined) return -1;
    return direction === 'desc' ? valB - valA : valA - valB;
  });

  // Find best scores
  const best = {};
  TRANSLATION_DIALECTS.forEach(d => {
    const values = sorted
      .map(entry => entry.translation_details ? entry.translation_details[d.key] : null)
      .filter(v => v !== null && v !== undefined);
    best[d.key] = values.length > 0 ? Math.max(...values) : null;
  });
  const avgValues = sorted
    .map(entry => entry.scores.sql_trans)
    .filter(v => v !== null && v !== undefined);
  best.avg = avgValues.length > 0 ? Math.max(...avgValues) : null;

  function getTransSortClass(key) {
    if (translationSort.key !== key) return '';
    return translationSort.direction === 'asc' ? 'sorted-asc' : 'sorted-desc';
  }

  // Build header
  let headerHTML = `
    <thead>
      <tr>
        <th class="rank-cell">#</th>
        <th data-tsort="model" class="${getTransSortClass('model')}">Model</th>
        <th data-tsort="avg" class="${getTransSortClass('avg')}">Avg</th>`;

  TRANSLATION_DIALECTS.forEach(d => {
    headerHTML += `<th data-tsort="${d.key}" class="${getTransSortClass(d.key)}">${d.label}</th>`;
  });
  headerHTML += `</tr></thead>`;

  // Build body
  let bodyHTML = '<tbody>';
  sorted.forEach((entry, index) => {
    const rank = index + 1;
    const rankClass = rank <= 3 ? `rank-${rank}` : '';
    const avg = entry.scores.sql_trans;
    const avgIsBest = avg !== null && best.avg !== null && Math.abs(avg - best.avg) < 0.01;

    bodyHTML += `<tr>
      <td class="rank-cell ${rankClass}">${rank}</td>
      <td class="model-cell">${escapeHTML(entry.model)}</td>
      <td class="score-cell overall-cell ${avgIsBest ? 'score-best' : ''}">
        ${avg !== null ? avg.toFixed(1) : '<span class="score-na">—</span>'}
      </td>`;

    TRANSLATION_DIALECTS.forEach(d => {
      const score = entry.translation_details ? entry.translation_details[d.key] : null;
      const isBest = score !== null && score !== undefined &&
                     best[d.key] !== null && Math.abs(score - best[d.key]) < 0.01;
      bodyHTML += `<td class="score-cell ${isBest ? 'score-best' : ''}">
        ${score !== null && score !== undefined ? score.toFixed(1) : '<span class="score-na">—</span>'}
      </td>`;
    });

    bodyHTML += '</tr>';
  });
  bodyHTML += '</tbody>';

  tableContainer.innerHTML = headerHTML + bodyHTML;
}

// --- Event Binding ---
function bindEvents() {
  // Sort by clicking column headers (event delegation)
  const table = document.getElementById('leaderboard-table');
  if (table) {
    table.addEventListener('click', (e) => {
      const th = e.target.closest('th[data-sort]');
      if (!th) return;

      const key = th.dataset.sort;
      if (currentSort.key === key) {
        currentSort.direction = currentSort.direction === 'desc' ? 'asc' : 'desc';
      } else {
        currentSort.key = key;
        currentSort.direction = 'desc';
      }
      renderTable();
    });
  }

  // Translation table sort
  const transTable = document.getElementById('translation-table');
  if (transTable) {
    transTable.addEventListener('click', (e) => {
      const th = e.target.closest('th[data-tsort]');
      if (!th) return;

      const key = th.dataset.tsort;
      if (translationSort.key === key) {
        translationSort.direction = translationSort.direction === 'desc' ? 'asc' : 'desc';
      } else {
        translationSort.key = key;
        translationSort.direction = 'desc';
      }
      renderTranslationTable();
    });
  }

  // Filter buttons
  document.querySelectorAll('[data-filter]').forEach(btn => {
    btn.addEventListener('click', () => {
      const newFilter = btn.dataset.filter;
      if (newFilter === currentFilter) return; // no-op if same

      currentFilter = newFilter;

      // Reset sort to overall when switching filters
      currentSort = { key: 'overall', direction: 'desc' };

      // Update active state
      document.querySelectorAll('[data-filter]').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      renderTable();
    });
  });

  // View tabs
  document.querySelectorAll('[data-view]').forEach(tab => {
    tab.addEventListener('click', () => {
      const view = tab.dataset.view;

      // Update tab active state
      document.querySelectorAll('[data-view]').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');

      // Toggle views
      const overallView = document.getElementById('view-overall');
      const translationView = document.getElementById('view-translation');

      if (view === 'overall') {
        overallView.style.display = '';
        translationView.style.display = 'none';
      } else {
        overallView.style.display = 'none';
        translationView.style.display = '';
        renderTranslationTable();
      }
    });
  });
}
