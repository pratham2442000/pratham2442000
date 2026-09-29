/**
 * AlphaDCA - Multi-Market Stock & Gold Investment Backtester
 * Client Logic, Chart.js Visualizations & Secure DOM Rendering
 */

document.addEventListener("DOMContentLoaded", () => {
  // State
  let currentChart = null;
  let currentChartTab = "portfolio"; // 'portfolio' | 'buypoints' | 'profit'
  let currentBacktestResult = null;
  let currentMetadata = null;
  let debounceTimer = null;
  let registeredStrategies = [];

  // DOM Elements
  const symbolInput = document.getElementById("symbolInput");
  const symbolDropdown = document.getElementById("symbolDropdown");
  const assetCurrencyTag = document.getElementById("assetCurrencyTag");
  const budgetCurrencySymbol = document.getElementById("budgetCurrencySymbol");
  const inputPrefix = document.getElementById("inputPrefix");
  const startDateInput = document.getElementById("startDateInput");
  const endDateInput = document.getElementById("endDateInput");
  const monthlyBudgetInput = document.getElementById("monthlyBudgetInput");
  const btnRunBacktest = document.getElementById("btnRunBacktest");
  const runSpinner = document.getElementById("runSpinner");
  const loadingBanner = document.getElementById("loadingBanner");
  const errorAlert = document.getElementById("errorAlert");
  const errorMessage = document.getElementById("errorMessage");
  const btnCloseAlert = document.getElementById("btnCloseAlert");
  const dashboardContent = document.getElementById("dashboardContent");
  const presetsContainer = document.getElementById("presetsContainer");
  const strategiesList = document.getElementById("strategiesList");
  const btnAddStrategy = document.getElementById("btnAddStrategy");
  const stepUpCheck = document.getElementById("stepUpCheck");
  const btnExportCsv = document.getElementById("btnExportCsv");

  // Formatters
  function formatCurrency(val, symbol = "$") {
    if (val === null || val === undefined || isNaN(val)) return "-";
    return symbol + Number(val).toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
  }

  function formatPct(val) {
    if (val === null || val === undefined || isNaN(val)) return "-";
    const sign = val > 0 ? "+" : "";
    return `${sign}${Number(val).toFixed(2)}%`;
  }

  function formatNumber(val, decimals = 2) {
    if (val === null || val === undefined || isNaN(val)) return "-";
    return Number(val).toLocaleString("en-US", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    });
  }

  // Strategy Colors Palette
  const STRAT_COLORS = [
    { border: "#10b981", bg: "rgba(16, 185, 129, 0.15)", dotClass: "dot-strategy-1" },
    { border: "#6366f1", bg: "rgba(99, 102, 241, 0.15)", dotClass: "dot-strategy-2" },
    { border: "#f59e0b", bg: "rgba(245, 158, 11, 0.15)", dotClass: "dot-strategy-3" },
    { border: "#f43f5e", bg: "rgba(244, 63, 94, 0.15)", dotClass: "dot-strategy-4" },
  ];

  // Set Default Date Range (5 Years)
  function setTimeframe(years) {
    const end = new Date();
    endDateInput.value = end.toISOString().split("T")[0];

    if (years === "max") {
      startDateInput.value = "2000-01-01";
    } else {
      const start = new Date();
      start.setFullYear(end.getFullYear() - parseInt(years, 10));
      startDateInput.value = start.toISOString().split("T")[0];
    }
  }
  setTimeframe(5);

  // Timeframe buttons listener
  document.querySelectorAll(".tf-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tf-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const years = btn.getAttribute("data-years");
      setTimeframe(years);
      runBacktest();
    });
  });

  // Popular Chips listener
  document.querySelectorAll(".chip-btn").forEach(chip => {
    chip.addEventListener("click", () => {
      document.querySelectorAll(".chip-btn").forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      const sym = chip.getAttribute("data-symbol");
      symbolInput.value = sym;
      updateCurrencyLabels(sym);
      runBacktest();
    });
  });

  // Evaluation Mode toggles
  const btnModeNormalized = document.getElementById("btnModeNormalized");
  const btnModeCustom = document.getElementById("btnModeCustom");
  const monthlyBudgetGroup = document.getElementById("monthlyBudgetGroup");

  btnModeNormalized.addEventListener("click", () => {
    btnModeNormalized.classList.add("active");
    btnModeCustom.classList.remove("active");
    monthlyBudgetGroup.classList.remove("hidden");
    document.querySelectorAll(".strat-custom-amount-wrapper").forEach(el => el.classList.add("hidden"));
  });

  btnModeCustom.addEventListener("click", () => {
    btnModeCustom.classList.add("active");
    btnModeNormalized.classList.remove("active");
    monthlyBudgetGroup.classList.add("hidden");
    document.querySelectorAll(".strat-custom-amount-wrapper").forEach(el => el.classList.remove("hidden"));
  });

  // Chart Tab Buttons
  document.querySelectorAll(".tab-btn").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      currentChartTab = tab.getAttribute("data-chart");
      if (currentBacktestResult) {
        renderActiveChart();
      }
    });
  });

  // Currency label updates
  function updateCurrencyLabels(symbol) {
    const sym = (symbol || "").toUpperCase();
    const isIndia = sym.endswith ? sym.endswith(".NS") : (sym.endsWith(".NS") || sym.endsWith(".BO") || sym.includes("NSEI") || sym.includes("BSESN"));
    const currencyStr = isIndia ? "INR (₹)" : "USD ($)";
    const symbolChar = isIndia ? "₹" : "$";

    assetCurrencyTag.textContent = currencyStr;
    budgetCurrencySymbol.textContent = symbolChar;
    inputPrefix.textContent = symbolChar;
    
    if (isIndia && Number(monthlyBudgetInput.value) <= 1000) {
      monthlyBudgetInput.value = 10000;
    } else if (!isIndia && Number(monthlyBudgetInput.value) > 5000) {
      monthlyBudgetInput.value = 500;
    }
  }

  symbolInput.addEventListener("change", () => {
    updateCurrencyLabels(symbolInput.value);
  });

  // Symbol Autocomplete
  symbolInput.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    const q = symbolInput.value.trim();
    if (!q) {
      symbolDropdown.style.display = "none";
      return;
    }
    debounceTimer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
        if (!res.ok) return;
        const matches = await res.json();
        renderAutocomplete(matches);
      } catch (err) {
        // Safe fallback
      }
    }, 250);
  });

  function renderAutocomplete(matches) {
    symbolDropdown.replaceChildren();
    if (!matches || matches.length === 0) {
      symbolDropdown.style.display = "none";
      return;
    }

    matches.forEach(m => {
      const item = document.createElement("div");
      item.className = "autocomplete-item";

      const symSpan = document.createElement("span");
      symSpan.className = "item-symbol";
      symSpan.textContent = m.symbol;

      const nameSpan = document.createElement("span");
      nameSpan.className = "item-name";
      nameSpan.textContent = `${m.name} (${m.currency || ""})`;

      item.appendChild(symSpan);
      item.appendChild(nameSpan);

      item.addEventListener("click", () => {
        symbolInput.value = m.symbol;
        updateCurrencyLabels(m.symbol);
        symbolDropdown.style.display = "none";
        runBacktest();
      });

      symbolDropdown.appendChild(item);
    });

    symbolDropdown.style.display = "block";
  }

  document.addEventListener("click", (e) => {
    if (!symbolDropdown.contains(e.target) && e.target !== symbolInput) {
      symbolDropdown.style.display = "none";
    }
  });

  // ==============================================================================
  // Dynamic Strategy Registry & Card Builder
  // ==============================================================================

  async function loadStrategies() {
    try {
      const res = await fetch("/api/strategies");
      if (!res.ok) return;
      registeredStrategies = await res.json();
    } catch (e) {
      console.warn("Could not load dynamic strategies:", e);
    }
  }

  function populateStrategySelect(selectEl, selectedId) {
    selectEl.replaceChildren();

    const scheduleOptGroup = document.createElement("optgroup");
    scheduleOptGroup.label = "📅 Schedule Strategies";

    const smartOptGroup = document.createElement("optgroup");
    smartOptGroup.label = "🎯 Smart & Technical Strategies";

    const customOptGroup = document.createElement("optgroup");
    customOptGroup.label = "⚙️ Custom User Strategies";

    const list = registeredStrategies.length > 0 ? registeredStrategies : [
      { id: "daily", name: "Daily Investment", category: "Schedule" },
      { id: "monthly_day", name: "Monthly (Configurable Day)", category: "Schedule" },
      { id: "weekly_day", name: "Weekly (Configurable Weekday)", category: "Schedule" },
      { id: "biweekly", name: "Bi-Weekly (Twice a Month)", category: "Schedule" },
      { id: "lump_sum", name: "Lump Sum (Day 1)", category: "Schedule" },
      { id: "buy_the_dip", name: "Buy The Dip (+ Monthly)", category: "Smart & Technical" },
    ];

    list.forEach(strat => {
      const opt = document.createElement("option");
      opt.value = strat.id;
      opt.textContent = strat.name;

      // Handle aliases
      if (strat.id === selectedId || 
         (selectedId === "monthly_1st" && strat.id === "monthly_day") || 
         (selectedId === "weekly" && strat.id === "weekly_day")) {
        opt.selected = true;
      }

      if (strat.category === "Schedule") {
        scheduleOptGroup.appendChild(opt);
      } else if (strat.category === "Custom") {
        customOptGroup.appendChild(opt);
      } else {
        smartOptGroup.appendChild(opt);
      }
    });

    selectEl.appendChild(scheduleOptGroup);
    selectEl.appendChild(smartOptGroup);
    if (customOptGroup.children.length > 0) {
      selectEl.appendChild(customOptGroup);
    }
  }

  function renderStrategyParameters(container, stratId, initialParams = {}) {
    container.replaceChildren();
    
    // Resolve alias
    let lookupId = stratId;
    if (stratId === "monthly_1st" || stratId === "monthly_15th" || stratId === "monthly_last") {
      lookupId = "monthly_day";
    } else if (stratId === "weekly") {
      lookupId = "weekly_day";
    }

    const strat = registeredStrategies.find(s => s.id === lookupId);
    if (!strat || !strat.parameters || strat.parameters.length === 0) {
      container.classList.add("hidden");
      return;
    }

    container.classList.remove("hidden");

    if (strat.description) {
      const hint = document.createElement("div");
      hint.className = "strategy-desc-hint";
      hint.textContent = strat.description;
      container.appendChild(hint);
    }

    strat.parameters.forEach(param => {
      const row = document.createElement("div");
      row.className = "param-field";

      const label = document.createElement("label");
      label.className = "param-label";
      label.textContent = param.label;
      if (param.hint) label.title = param.hint;

      let input;
      let initialVal = (initialParams && initialParams[param.name] !== undefined)
        ? initialParams[param.name]
        : param.default;

      // Handle preset alias conversion for day_of_month
      if (param.name === "day_of_month") {
        if (stratId === "monthly_1st") initialVal = 1;
        if (stratId === "monthly_15th") initialVal = 15;
        if (stratId === "monthly_last") initialVal = "last";
      }

      if (param.type === "select") {
        input = document.createElement("select");
        input.className = "param-select";
        input.setAttribute("data-param-name", param.name);

        param.options.forEach(optVal => {
          const opt = document.createElement("option");
          opt.value = optVal;
          opt.textContent = optVal;
          if (String(optVal) === String(initialVal)) opt.selected = true;
          input.appendChild(opt);
        });
      } else {
        input = document.createElement("input");
        input.type = "number";
        input.className = "param-input";
        input.setAttribute("data-param-name", param.name);
        if (param.min !== null && param.min !== undefined) input.min = param.min;
        if (param.max !== null && param.max !== undefined) input.max = param.max;
        if (param.step !== null && param.step !== undefined) input.step = param.step;
        input.value = initialVal;
      }

      row.appendChild(label);
      row.appendChild(input);
      container.appendChild(row);
    });
  }

  function createStrategyCard(idx, config = {}) {
    const colorObj = STRAT_COLORS[idx % STRAT_COLORS.length];
    const card = document.createElement("div");
    card.className = "strategy-card";
    card.setAttribute("data-strat-idx", idx);

    const topRow = document.createElement("div");
    topRow.className = "strat-top";

    const dot = document.createElement("div");
    dot.className = `strat-indicator ${colorObj.dotClass}`;

    const inputName = document.createElement("input");
    inputName.type = "text";
    inputName.className = "strat-name-input form-input-clean";
    inputName.value = config.name || (idx === 0 ? "Daily Investment" : (idx === 1 ? "1st of Month SIP" : `Strategy ${idx + 1}`));

    topRow.appendChild(dot);
    topRow.appendChild(inputName);

    if (idx >= 2) {
      const btnRemove = document.createElement("button");
      btnRemove.type = "button";
      btnRemove.className = "btn-text-action";
      btnRemove.style.color = "var(--accent-rose)";
      btnRemove.style.marginLeft = "auto";
      btnRemove.textContent = "Remove";
      btnRemove.addEventListener("click", () => card.remove());
      topRow.appendChild(btnRemove);
    }

    const configGrid = document.createElement("div");
    configGrid.className = "strat-config-grid";

    const select = document.createElement("select");
    select.className = "form-select strat-freq-select";
    const initialFreq = config.frequency || (idx === 0 ? "daily" : "monthly_day");
    populateStrategySelect(select, initialFreq);

    const customWrapper = document.createElement("div");
    customWrapper.className = `strat-custom-amount-wrapper ${btnModeNormalized.classList.contains("active") ? "hidden" : ""}`;

    const amountInput = document.createElement("input");
    amountInput.type = "number";
    amountInput.className = "form-input form-input-sm strat-amount-input";
    amountInput.value = config.amount || (idx === 0 ? "25" : "500");

    customWrapper.appendChild(amountInput);
    configGrid.appendChild(select);
    configGrid.appendChild(customWrapper);

    const paramsContainer = document.createElement("div");
    paramsContainer.className = "strat-params-container hidden";

    select.addEventListener("change", () => {
      const selectedStrat = registeredStrategies.find(s => s.id === select.value);
      if (selectedStrat && (inputName.value.startsWith("Strategy ") || inputName.value === "")) {
        inputName.value = selectedStrat.name;
      }
      renderStrategyParameters(paramsContainer, select.value, {});
    });

    card.appendChild(topRow);
    card.appendChild(configGrid);
    card.appendChild(paramsContainer);

    renderStrategyParameters(paramsContainer, select.value, config.params || {});

    return card;
  }

  // Add Strategy dynamic card button
  btnAddStrategy.addEventListener("click", () => {
    const cards = strategiesList.querySelectorAll(".strategy-card");
    if (cards.length >= 4) {
      alert("You can compare up to 4 strategies simultaneously.");
      return;
    }
    const nextIdx = cards.length;
    const defaultFreq = nextIdx === 2 ? "buy_the_dip" : "weekly_day";
    const card = createStrategyCard(nextIdx, {
      name: nextIdx === 2 ? "Buy The Dip" : `Strategy ${nextIdx + 1}`,
      frequency: defaultFreq,
      amount: 250,
      params: {}
    });
    strategiesList.appendChild(card);
  });

  // Load Presets
  async function loadPresets() {
    try {
      const res = await fetch("/api/presets");
      if (!res.ok) return;
      const presets = await res.json();
      presetsContainer.replaceChildren();

      presets.forEach(p => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "preset-chip";
        btn.textContent = p.title;

        btn.addEventListener("click", () => {
          applyPreset(p);
        });

        presetsContainer.appendChild(btn);
      });
    } catch (e) {
      // ignore
    }
  }

  function applyPreset(p) {
    symbolInput.value = p.symbol;
    updateCurrencyLabels(p.symbol);
    monthlyBudgetInput.value = p.monthlyBudget;
    
    // Set timeframe if provided
    const tfBtn = document.querySelector(`.tf-btn[data-years="${p.period.replace('y', '')}"]`);
    if (tfBtn) {
      document.querySelectorAll(".tf-btn").forEach(b => b.classList.remove("active"));
      tfBtn.classList.add("active");
      setTimeframe(p.period.replace("y", ""));
    }

    // Set strategies
    strategiesList.replaceChildren();
    p.strategies.forEach((st, idx) => {
      const card = createStrategyCard(idx, st);
      strategiesList.appendChild(card);
    });

    runBacktest();
  }

  // Run Backtest
  async function runBacktest() {
    hideError();
    const symbol = symbolInput.value.trim();
    if (!symbol) {
      showError("Please enter a stock ticker, ETF, index, or Gold symbol.");
      return;
    }

    const budgetMode = btnModeNormalized.classList.contains("active") ? "normalized" : "custom";
    const monthlyBudget = parseFloat(monthlyBudgetInput.value) || 500;
    const isStepUp = stepUpCheck.checked;

    // Collect strategies
    const stratCards = strategiesList.querySelectorAll(".strategy-card");
    const strategies = [];
    stratCards.forEach((card, idx) => {
      const nameInput = card.querySelector(".strat-name-input");
      const freqSelect = card.querySelector(".strat-freq-select");
      const amountInput = card.querySelector(".strat-amount-input");

      // Extract custom parameters
      const params = {};
      const paramInputs = card.querySelectorAll(".strat-params-container [data-param-name]");
      paramInputs.forEach(pInput => {
        const pName = pInput.getAttribute("data-param-name");
        const val = pInput.value;
        params[pName] = isNaN(val) ? val : parseFloat(val);
      });

      strategies.push({
        id: `strat_${idx + 1}`,
        name: nameInput.value.trim() || `Strategy ${idx + 1}`,
        frequency: freqSelect.value,
        amount: parseFloat(amountInput.value) || 100,
        step_up_pct: isStepUp ? 10.0 : 0.0,
        params: params
      });
    });

    if (strategies.length === 0) {
      showError("Please configure at least one strategy to backtest.");
      return;
    }

    const payload = {
      symbol: symbol,
      startDate: startDateInput.value || null,
      endDate: endDateInput.value || null,
      budgetMode: budgetMode,
      monthlyBudget: monthlyBudget,
      strategies: strategies
    };

    setLoading(true);

    try {
      const response = await fetch("/api/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Backtest request failed.");
      }

      currentBacktestResult = data.result;
      currentMetadata = data.metadata;

      renderResults();
    } catch (err) {
      showError(err.message || "Failed to run simulation. Please check your inputs and network connection.");
    } finally {
      setLoading(false);
    }
  }

  btnRunBacktest.addEventListener("click", runBacktest);

  function setLoading(isLoading) {
    if (isLoading) {
      runSpinner.classList.remove("hidden");
      loadingBanner.classList.remove("hidden");
      btnRunBacktest.disabled = true;
    } else {
      runSpinner.classList.add("hidden");
      loadingBanner.classList.add("hidden");
      btnRunBacktest.disabled = false;
    }
  }

  function showError(msg) {
    errorMessage.textContent = msg;
    errorAlert.classList.remove("hidden");
    errorAlert.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function hideError() {
    errorAlert.classList.add("hidden");
  }

  btnCloseAlert.addEventListener("click", hideError);

  // Render Full Results
  function renderResults() {
    const meta = currentMetadata;
    const res = currentBacktestResult;
    const currSym = meta.currencySymbol || "$";

    // Hero Overview
    document.getElementById("heroSymbol").textContent = meta.symbol;
    document.getElementById("heroName").textContent = meta.name;
    document.getElementById("heroMarket").textContent = meta.market;
    document.getElementById("heroCurrency").textContent = `${meta.currency} (${currSym})`;
    document.getElementById("heroDateRange").textContent = `${meta.startDate} to ${meta.endDate}`;
    document.getElementById("heroTradingDays").textContent = `${meta.totalDays.toLocaleString()} Trading Days`;
    document.getElementById("heroPrice").textContent = formatCurrency(meta.latestPrice, currSym);

    // Winner Callout
    const winnerCallout = document.getElementById("winnerCallout");
    const winnerHeadline = document.getElementById("winnerHeadline");
    const winnerInsight = document.getElementById("winnerInsight");

    if (res.comparison) {
      winnerHeadline.textContent = `Winner: ${res.comparison.winnerName}`;
      winnerInsight.textContent = res.comparison.insight;
      winnerCallout.classList.remove("hidden");
    } else {
      winnerCallout.classList.add("hidden");
    }

    // Render Strategy KPI Cards
    renderKpiCards(res.strategies, res.comparison, currSym);

    // Render Active Chart
    renderActiveChart();

    // Render Yearly Breakdown Table
    renderYearlyTable(res.strategies, currSym);

    // Render Transaction Log
    renderTransactionLog(res.strategies, currSym);
  }

  // Render KPI Cards
  function renderKpiCards(strategies, comparison, currSym) {
    const container = document.getElementById("strategyKpiGrid");
    container.replaceChildren();

    strategies.forEach((strat, idx) => {
      const sum = strat.summary;
      const isWinner = comparison && comparison.winnerId === strat.id;
      const colorObj = STRAT_COLORS[idx % STRAT_COLORS.length];

      const card = document.createElement("div");
      card.className = `kpi-card ${isWinner ? "kpi-card-winner" : ""}`;

      // Card Header
      const head = document.createElement("div");
      head.className = "kpi-card-header";

      const title = document.createElement("div");
      title.className = "kpi-strat-title";

      const dot = document.createElement("div");
      dot.className = `strat-indicator ${colorObj.dotClass}`;

      const titleText = document.createElement("span");
      titleText.textContent = strat.name;

      title.appendChild(dot);
      title.appendChild(titleText);
      head.appendChild(title);

      if (isWinner) {
        const winPill = document.createElement("span");
        winPill.className = "winner-pill";
        winPill.textContent = "Best Performer";
        head.appendChild(winPill);
      }

      card.appendChild(head);

      // Main Metric: Ending Portfolio Value
      const mainMetric = document.createElement("div");
      mainMetric.className = "kpi-main-metric";

      const label = document.createElement("div");
      label.className = "kpi-label";
      label.textContent = "Ending Portfolio Value";

      const val = document.createElement("div");
      val.className = "kpi-val-highlight";
      val.textContent = formatCurrency(sum.finalValue, currSym);

      const gainBadge = document.createElement("div");
      const isGain = sum.netProfit >= 0;
      gainBadge.className = `kpi-gain-badge ${isGain ? "gain-positive" : "gain-negative"}`;
      gainBadge.textContent = `${formatCurrency(sum.netProfit, currSym)} (${formatPct(sum.totalReturnPct)})`;

      mainMetric.appendChild(label);
      mainMetric.appendChild(val);
      mainMetric.appendChild(gainBadge);
      card.appendChild(mainMetric);

      // Sub-metrics Grid
      const subGrid = document.createElement("div");
      subGrid.className = "kpi-metrics-grid";

      const metrics = [
        { label: "Total Invested", val: formatCurrency(sum.totalInvested, currSym) },
        { label: "Annualized XIRR", val: `${sum.xirr}% / yr` },
        { label: "CAGR", val: `${sum.cagr}% / yr` },
        { label: "Units Accumulated", val: formatNumber(sum.totalUnits, 3) },
        { label: "Avg Cost Basis", val: formatCurrency(sum.avgCostBasis, currSym) },
        { label: "Max Drawdown", val: `${sum.maxDrawdown}%` },
      ];

      metrics.forEach(m => {
        const item = document.createElement("div");
        item.className = "kpi-subitem";

        const mLabel = document.createElement("div");
        mLabel.className = "kpi-subitem-label";
        mLabel.textContent = m.label;

        const mVal = document.createElement("div");
        mVal.className = "kpi-subitem-val";
        mVal.textContent = m.val;

        item.appendChild(mLabel);
        item.appendChild(mVal);
        subGrid.appendChild(item);
      });

      card.appendChild(subGrid);
      container.appendChild(card);
    });
  }

  // Render Charts with Chart.js
  function renderActiveChart() {
    const ctx = document.getElementById("mainChart").getContext("2d");
    const res = currentBacktestResult;
    const meta = currentMetadata;
    const currSym = meta.currencySymbol || "$";

    if (currentChart) {
      currentChart.destroy();
    }

    const labels = res.dates;

    if (currentChartTab === "portfolio") {
      // Multi-line chart: Portfolio values + invested capital curves
      const datasets = [];

      res.strategies.forEach((strat, idx) => {
        const color = STRAT_COLORS[idx % STRAT_COLORS.length];
        const sampledVals = res.chartSeries[idx].values;

        // Portfolio Value line
        datasets.push({
          label: `${strat.name} (Value)`,
          data: sampledVals,
          borderColor: color.border,
          backgroundColor: color.bg,
          fill: false,
          borderWidth: 2.5,
          tension: 0.15,
          pointRadius: 0,
          pointHoverRadius: 5
        });

        // Invested curve line (dotted/subtle)
        const sampledInv = res.chartSeries[idx].invested;
        datasets.push({
          label: `${strat.name} (Invested)`,
          data: sampledInv,
          borderColor: color.border,
          borderDash: [5, 5],
          borderWidth: 1.5,
          fill: false,
          pointRadius: 0,
          pointHoverRadius: 3
        });
      });

      currentChart = new Chart(ctx, {
        type: "line",
        data: { labels, datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          scales: {
            x: {
              grid: { color: "rgba(255, 255, 255, 0.05)" },
              ticks: { color: "#94a3b8", maxTicksLimit: 10 }
            },
            y: {
              grid: { color: "rgba(255, 255, 255, 0.05)" },
              ticks: {
                color: "#94a3b8",
                callback: val => formatCurrency(val, currSym)
              }
            }
          },
          plugins: {
            legend: {
              labels: { color: "#f8fafc", boxWidth: 14, font: { family: "Inter", size: 12 } }
            },
            tooltip: {
              backgroundColor: "#1e293b",
              titleColor: "#f8fafc",
              bodyColor: "#cbd5e1",
              borderColor: "rgba(255, 255, 255, 0.1)",
              borderWidth: 1,
              callbacks: {
                label: context => ` ${context.dataset.label}: ${formatCurrency(context.parsed.y, currSym)}`
              }
            }
          }
        }
      });

    } else if (currentChartTab === "buypoints") {
      // Stock Close Price curve with scatter markers of buy events
      const priceDataset = {
        label: `${meta.symbol} Price`,
        data: res.prices,
        borderColor: "#38bdf8",
        backgroundColor: "rgba(56, 189, 248, 0.08)",
        fill: true,
        borderWidth: 2,
        tension: 0.1,
        pointRadius: 0,
        yAxisID: "y"
      };

      const datasets = [priceDataset];

      currentChart = new Chart(ctx, {
        type: "line",
        data: { labels, datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            x: {
              grid: { color: "rgba(255, 255, 255, 0.05)" },
              ticks: { color: "#94a3b8", maxTicksLimit: 10 }
            },
            y: {
              grid: { color: "rgba(255, 255, 255, 0.05)" },
              ticks: {
                color: "#94a3b8",
                callback: val => formatCurrency(val, currSym)
              }
            }
          },
          plugins: {
            legend: { labels: { color: "#f8fafc" } },
            tooltip: {
              callbacks: {
                label: context => ` Price: ${formatCurrency(context.parsed.y, currSym)}`
              }
            }
          }
        }
      });

    } else if (currentChartTab === "profit") {
      // Net Return % over time
      const datasets = [];

      res.strategies.forEach((strat, idx) => {
        const color = STRAT_COLORS[idx % STRAT_COLORS.length];
        const sampledVals = res.chartSeries[idx].values;
        const sampledInv = res.chartSeries[idx].invested;

        const returnPcts = sampledVals.map((v, i) => {
          const inv = sampledInv[i];
          if (inv <= 0) return 0;
          return Number(((v - inv) / inv * 100).toFixed(2));
        });

        datasets.push({
          label: `${strat.name} (% Gain)`,
          data: returnPcts,
          borderColor: color.border,
          backgroundColor: color.bg,
          fill: false,
          borderWidth: 2.2,
          tension: 0.15,
          pointRadius: 0
        });
      });

      currentChart = new Chart(ctx, {
        type: "line",
        data: { labels, datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          scales: {
            x: {
              grid: { color: "rgba(255, 255, 255, 0.05)" },
              ticks: { color: "#94a3b8", maxTicksLimit: 10 }
            },
            y: {
              grid: { color: "rgba(255, 255, 255, 0.05)" },
              ticks: {
                color: "#94a3b8",
                callback: val => `${val}%`
              }
            }
          },
          plugins: {
            legend: { labels: { color: "#f8fafc" } },
            tooltip: {
              callbacks: {
                label: context => ` ${context.dataset.label}: ${context.parsed.y}%`
              }
            }
          }
        }
      });
    }
  }

  // Render Yearly Breakdown Table
  function renderYearlyTable(strategies, currSym) {
    const head = document.getElementById("yearlyTableHead");
    const body = document.getElementById("yearlyTableBody");

    // Rebuild header
    head.replaceChildren();
    const thYear = document.createElement("th");
    thYear.textContent = "Year";
    head.appendChild(thYear);

    strategies.forEach(st => {
      const thInv = document.createElement("th");
      thInv.textContent = `${st.name} Invested`;
      const thVal = document.createElement("th");
      thVal.textContent = `${st.name} Value`;
      const thGain = document.createElement("th");
      thGain.textContent = `${st.name} Return`;

      head.appendChild(thInv);
      head.appendChild(thVal);
      head.appendChild(thGain);
    });

    // Rebuild rows
    body.replaceChildren();
    const yearsCount = strategies[0]?.yearlyBreakdown?.length || 0;

    for (let i = 0; i < yearsCount; i++) {
      const tr = document.createElement("tr");
      const year = strategies[0].yearlyBreakdown[i].year;

      const tdYear = document.createElement("td");
      tdYear.style.fontWeight = "700";
      tdYear.style.color = "#ffffff";
      tdYear.textContent = year;
      tr.appendChild(tdYear);

      strategies.forEach(st => {
        const rowData = st.yearlyBreakdown[i];
        
        const tdInv = document.createElement("td");
        tdInv.textContent = formatCurrency(rowData.totalInvested, currSym);

        const tdVal = document.createElement("td");
        tdVal.style.fontWeight = "600";
        tdVal.style.color = "#38bdf8";
        tdVal.textContent = formatCurrency(rowData.endingValue, currSym);

        const tdGain = document.createElement("td");
        const isPos = rowData.netGain >= 0;
        tdGain.style.color = isPos ? "var(--accent-emerald)" : "var(--accent-rose)";
        tdGain.style.fontWeight = "600";
        tdGain.textContent = `${formatCurrency(rowData.netGain, currSym)} (${formatPct(rowData.gainPct)})`;

        tr.appendChild(tdInv);
        tr.appendChild(tdVal);
        tr.appendChild(tdGain);
      });

      body.appendChild(tr);
    }
  }

  // Render Transaction Log
  function renderTransactionLog(strategies, currSym) {
    const tbody = document.getElementById("txTableBody");
    tbody.replaceChildren();

    // Combine transactions from strategies and sort by date descending
    const allTx = [];
    strategies.forEach(st => {
      (st.transactions || []).forEach(tx => {
        allTx.push({ ...tx, strategyName: st.name });
      });
    });

    allTx.sort((a, b) => b.date.localeCompare(a.date));

    // Show up to 100 recent orders in the preview table
    const preview = allTx.slice(0, 100);

    preview.forEach(tx => {
      const tr = document.createElement("tr");

      const tdDate = document.createElement("td");
      tdDate.textContent = tx.date;

      const tdStrat = document.createElement("td");
      tdStrat.style.fontWeight = "600";
      tdStrat.textContent = tx.strategyName;

      const tdType = document.createElement("td");
      const typeSpan = document.createElement("span");
      typeSpan.style.color = "var(--accent-emerald)";
      typeSpan.style.fontWeight = "700";
      typeSpan.textContent = tx.type;
      tdType.appendChild(typeSpan);

      const tdPrice = document.createElement("td");
      tdPrice.textContent = formatCurrency(tx.price, currSym);

      const tdAmt = document.createElement("td");
      tdAmt.textContent = formatCurrency(tx.amount, currSym);

      const tdShares = document.createElement("td");
      tdShares.textContent = formatNumber(tx.shares, 4);

      const tdTotShares = document.createElement("td");
      tdTotShares.textContent = formatNumber(tx.totalShares, 4);

      const tdTotCap = document.createElement("td");
      tdTotCap.textContent = formatCurrency(tx.cumulativeInvested, currSym);

      tr.appendChild(tdDate);
      tr.appendChild(tdStrat);
      tr.appendChild(tdType);
      tr.appendChild(tdPrice);
      tr.appendChild(tdAmt);
      tr.appendChild(tdShares);
      tr.appendChild(tdTotShares);
      tr.appendChild(tdTotCap);

      tbody.appendChild(tr);
    });
  }

  // Export CSV
  btnExportCsv.addEventListener("click", () => {
    if (!currentBacktestResult) {
      alert("Please run a backtest before exporting.");
      return;
    }

    const strategies = currentBacktestResult.strategies;
    const allTx = [];
    strategies.forEach(st => {
      (st.transactions || []).forEach(tx => {
        allTx.push({ ...tx, strategyName: st.name });
      });
    });

    allTx.sort((a, b) => a.date.localeCompare(b.date));

    if (allTx.length === 0) {
      alert("No transaction records found.");
      return;
    }

    let csv = "Date,Strategy,Action,Execution_Price,Cash_Invested,Units_Bought,Cumulative_Units,Total_Invested\n";
    allTx.forEach(t => {
      csv += `${t.date},"${t.strategyName}",${t.type},${t.price},${t.amount},${t.shares},${t.totalShares},${t.cumulativeInvested}\n`;
    });

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `backtest_${currentMetadata.symbol}_${new Date().toISOString().split("T")[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  });

  // Initial Load
  async function init() {
    await loadStrategies();
    await loadPresets();
    runBacktest();
  }
  init();
});
