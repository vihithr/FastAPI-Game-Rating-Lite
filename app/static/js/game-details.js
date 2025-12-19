// /app/static/js/game-details.js

document.addEventListener('DOMContentLoaded', () => {
    // 这部分代码只在含有 id="evaluation-data" 的页面 (详情页) 上执行
    const evaluationDataEl = document.getElementById('evaluation-data');
    if (!evaluationDataEl) {
        return;
    }

    // --- 1. 全局变量和初始化数据 ---
    const evaluationData = JSON.parse(evaluationDataEl.textContent);
    const sessionData = JSON.parse(document.getElementById('session-data').textContent);
    const configData = JSON.parse(document.getElementById('config-data')?.textContent || '{}');
    const gameId = document.getElementById('comment-form')?.dataset.gameId;
    let qualityChart, difficultyChart;
    
    // 从配置读取评分范围
    const difficultyMin = configData.difficulty_min || 1;
    const difficultyMax = configData.difficulty_max || 60;
    const difficultyMaxScore = configData.difficulty_max_score || 60;
    const qualityMin = configData.quality_min || 1;
    const qualityMax = configData.quality_max || 10;
    
    // 用户评分数据（从模板传入或API获取）
    const userRatingsDataEl = document.getElementById('user-ratings-data');
    let userRatings = userRatingsDataEl ? JSON.parse(userRatingsDataEl.textContent) : {};

    // --- 2. 您的辅助函数 (保留) ---
    const toast = document.getElementById('toast-notification');
    function showToast(message, isError = false) {
        toast.textContent = message;
        toast.style.backgroundColor = isError ? 'var(--pico-color-red-500)' : 'var(--pico-contrast)';
        toast.classList.add('show');
        setTimeout(() => { toast.classList.remove('show'); }, 3000);
    }
    function escapeHTML(str) {
        if (str === null || str === undefined) return '';
        const p = document.createElement('p');
        p.textContent = str;
        return p.innerHTML;
    }
    if (window.ChartDataLabels) {
        Chart.register(window.ChartDataLabels);
    }

    // Quality Rating Chart Function
    function createOrUpdateQualityChart(scores) {
        const ctx = document.getElementById('qualityChart').getContext('2d');
        if (qualityChart) qualityChart.destroy();

        const labels = scores.map(s => s.category);
        const data = scores.map(s => s.raw_value);

        const isDarkMode = document.documentElement.dataset.theme === 'dark';
        const gridColor = isDarkMode ? 'rgba(255, 255, 255, 0.15)' : 'rgba(0, 0, 0, 0.1)';
        const labelColor = isDarkMode ? 'rgba(255, 255, 255, 0.9)' : 'rgba(0, 0, 0, 0.8)';
        
        const qualityGradient = ctx.createLinearGradient(0, 0, 0, ctx.canvas.height);
        qualityGradient.addColorStop(0, 'rgba(54, 162, 235, 0.6)');
        qualityGradient.addColorStop(1, 'rgba(54, 162, 235, 0.1)');
        const qualityBorderColor = 'rgb(54, 162, 235)';

        qualityChart = new Chart(ctx, {
            type: 'radar',
            data: {
                labels: labels,
                datasets: [{
                    label: '品质评分 (AVG)',
                    data: data,
                    fill: true,
                    backgroundColor: qualityGradient,
                    borderColor: qualityBorderColor,
                    pointBackgroundColor: qualityBorderColor,
                    pointBorderColor: '#fff',
                    pointHoverBackgroundColor: '#fff',
                    pointHoverBorderColor: qualityBorderColor
                }]
            },
            options: {
                maintainAspectRatio: false,
                scales: {
                    r: {
                        beginAtZero: true, max: 10,
                        grid: { color: gridColor },
                        angleLines: { color: gridColor, borderDash: [4, 4] },
                        // --- V3 OPTIMIZATION: Restore and style corner labels ---
                        pointLabels: {
                            display: true,
                            color: labelColor,
                            font: { size: 14, weight: 'bold' },
                            backdropColor: isDarkMode ? 'rgba(40, 42, 54, 0.7)' : 'rgba(255, 255, 255, 0.75)',
                            backdropPadding: 5,
                            borderRadius: 5
                        },
                        ticks: { display: false, stepSize: 2 }
                    }
                },
                plugins: {
                    // --- V3 OPTIMIZATION: Datalabel now only shows the score ---
					datalabels: {
						color: isDarkMode ? '#fff' : '#000',
						font: { weight: 'bold', size: 14 },
						formatter: (value) => value.toFixed(1),
                        backgroundColor: isDarkMode ? 'rgba(54, 162, 235, 0.8)' : 'rgba(255, 255, 255, 0.8)',
                        borderColor: qualityBorderColor,
                        borderWidth: 1,
                        borderRadius: 4,
                        padding: 4,
                        offset: 8,
                        anchor: 'end',
					},
                    tooltip: {
                        displayColors: false,
                        yAlign: 'bottom',
                        padding: 10,
                        caretPadding: 10,
                        caretSize: 8,
                        cornerRadius: 6,
                        callbacks: {
                            title: (context) => context[0].label,
                            label: (context) => `${context.dataset.label}: ${context.raw.toFixed(2)}`
                        }
                    }
                },
                elements: {
                    point: {
                        radius: 5,
                        hoverRadius: 8
                    },
                    line: {
                        borderWidth: 3,
                        tension: 0.02
                    }
                }
            }
        });
    }

    // 难度图表函数，现在它依赖传入的 scores 来获取所有信息
    function createOrUpdateDifficultyChart(scores) {
        const ctx = document.getElementById('difficultyChart').getContext('2d');
        if (difficultyChart) difficultyChart.destroy();
        const labels = scores.map(s => s.category);
        const data = scores.map(s => s.raw_value);
        const realmTooltips = scores.map(s => s.value); // 从传入的scores动态生成
        const isDarkMode = document.documentElement.dataset.theme === 'dark';
        // ... 您原有完整的难度图表创建代码 (从 const gridColor 开始到 new Chart(...) 结束)
        // 注意：内部的 formatter 和 callbacks 不再依赖全局变量，而是直接使用这里的 realmTooltips
        const gridColor = isDarkMode ? 'rgba(255, 255, 255, 0.15)' : 'rgba(0, 0, 0, 0.1)';
        const labelColor = isDarkMode ? 'rgba(255, 255, 255, 0.9)' : 'rgba(0, 0, 0, 0.8)';
        const difficultyGradient = ctx.createLinearGradient(0, 0, 0, ctx.canvas.height);
        difficultyGradient.addColorStop(0, 'rgba(255, 99, 132, 0.6)');
        difficultyGradient.addColorStop(1, 'rgba(255, 99, 132, 0.1)');
        const difficultyBorderColor = 'rgb(255, 99, 132)'; // <-- 定义变量
        difficultyChart = new Chart(ctx, {
            type: 'radar',
            data: {
                labels: labels,
                datasets: [{
                    label: '难度评分 (AVG)',
                    data: data,
                    fill: true,
                    backgroundColor: difficultyGradient,
                    borderColor: difficultyBorderColor,
                    pointBackgroundColor: difficultyBorderColor,
                    pointBorderColor: '#fff',
                    pointHoverBackgroundColor: '#fff',
                    pointHoverBorderColor: difficultyBorderColor
                }]
            },
            options: {
                maintainAspectRatio: false,
                scales: {
                    r: {
                        beginAtZero: true, max: difficultyMax,
                        grid: { color: gridColor },
                        angleLines: { color: gridColor, borderDash: [4, 4] },
                        // --- V3 OPTIMIZATION: Restore and style corner labels ---
                        pointLabels: {
                            display: true,
                            color: labelColor,
                            font: { size: 14, weight: 'bold' },
                            backdropColor: isDarkMode ? 'rgba(40, 42, 54, 0.7)' : 'rgba(255, 255, 255, 0.75)',
                            backdropPadding: 5,
                            borderRadius: 5
                        },
                        ticks: { display: false, stepSize: 10 }
                    }
                },
                plugins: {
					// --- V3 OPTIMIZATION: Datalabel shows both description and score ---
                    datalabels: {
						color: isDarkMode ? '#fff' : '#000',
						font: { weight: 'bold', size: 12, lineHeight: 1.3 },
                        textAlign: 'center',
                        backgroundColor: isDarkMode ? 'rgba(255, 99, 132, 0.8)' : 'rgba(255, 255, 255, 0.8)',
                        borderColor: difficultyBorderColor,
                        borderWidth: 1,
                        borderRadius: 4,
                        padding: { top: 4, bottom: 2, left: 6, right: 6 },
                        offset: 8,
                        anchor: 'end',
						formatter: (value, context) => {
                            const realmLabel = realmTooltips.map(item => item.split(' ')[0])[context.dataIndex];
                            return `${realmLabel}\n(${value.toFixed(1)})`;
                        }
					},
                    tooltip: {
                        displayColors: false,
                        yAlign: 'bottom',
                        padding: 10,
                        caretPadding: 10,
                        caretSize: 8,
                        cornerRadius: 6,
                        callbacks: {
                            // Show the full "realm (score/60)" string in tooltip
                            title: (context) => context[0].label,
                            label: (context) => realmTooltips[context.dataIndex]
                        }
                    }
                },
                elements: {
                    point: {
                        radius: 5,
                        hoverRadius: 8
                    },
                    line: {
                        borderWidth: 3,
                        tension: 0.02
                    }
                }
            }
        });
    }

    // --- 4. 核心逻辑：情境选择与UI更新 ---
    const diffSelector = document.getElementById('difficulty-context-selector');
    const shipSelector = document.getElementById('ship-context-selector');
    const qualityDisplay = document.getElementById('overall-quality-display');
    const difficultyDisplay = document.getElementById('overall-difficulty-display');
    const contextInfo = document.getElementById('context-info');
    const formContextLabel = document.getElementById('form-context-label');
    const formDiffId = document.getElementById('form-difficulty-id'); // 可能不存在，保持向后兼容
    const formShipId = document.getElementById('form-ship-id');       // 可能不存在
    
    // 难度评分表单的选择器
    const formDiffSelector = document.getElementById('form-difficulty-selector');
    const formShipSelector = document.getElementById('form-ship-selector');
    const difficultyRatingStatus = document.getElementById('difficulty-rating-status');

	function updateUIForContext() {
		if (!diffSelector || !shipSelector) return;

		const diffId = diffSelector.value;
		const shipId = shipSelector.value;
		const contextKey = `d${diffId}_s${shipId}`;
		const contextData = evaluationData.difficulty_scores_by_context[contextKey];
		
		// 获取显示境界的元素
		const realmDisplay = document.getElementById('overall-difficulty-realm');

		// 从配置读取难度维度
		const configData = JSON.parse(document.getElementById('config-data')?.textContent || '{}');
		const difficultyDims = configData.difficulty_dimensions || [];
		const defaultScores = difficultyDims.map(dim => ({
			"category": dim.name,
			"raw_value": 0,
			"value": "N/A"
		}));
		
		// 更新雷达图
        createOrUpdateDifficultyChart(contextData ? contextData.categories : defaultScores);
		
		// --- 核心修改：根据情境动态更新分数和境界 ---
		if (contextData) {
			// 如果该情境有数据
			difficultyDisplay.textContent = `${contextData.overall_avg.toFixed(2)}`;
			realmDisplay.textContent = getDifficultyRealmJS(contextData.overall_avg); // <--- 动态计算并更新境界
		} else if (diffId === '0' && shipId === '0') {
			// 如果选择的是“游戏总体”，但它恰好没有任何评分
			difficultyDisplay.textContent = evaluationData.overall_difficulty_score > 0 ? evaluationData.overall_difficulty_score.toFixed(2) : '暂无评分';
			realmDisplay.textContent = evaluationData.overall_difficulty_realm; // <--- 使用后端传来的总境界
		} else {
			// 如果选择的是一个具体情境，但该情境没有任何评分
			difficultyDisplay.textContent = '暂无评分';
			realmDisplay.textContent = 'N/A'; // <--- 将境界设为 N/A
		}
		
		// --- 后续的UI更新逻辑保持不变 ---
		const diffText = diffSelector.options[diffSelector.selectedIndex].text.trim();
		const shipText = shipSelector.options[shipSelector.selectedIndex].text.trim();
		const currentContextText = `${diffText} | ${shipText}`;
		
		contextInfo.textContent = `当前情境 (${contextData ? contextData.total_ratings : 0}条评分)`;
		if(formContextLabel) formContextLabel.textContent = currentContextText;
        updateOptionCounts(); // 选中情境后刷新数量，保持与另一筛选联动
	}
    if (diffSelector && shipSelector) {
        diffSelector.addEventListener('change', () => {
            updateUIForContext();
        });
        shipSelector.addEventListener('change', () => {
            updateUIForContext();
        });
    }
    
    // --- 4.1 选项文字带上评分数量 ---
    function updateOptionCounts() {
        if (!diffSelector && !shipSelector) return;
        const contextMap = evaluationData.difficulty_scores_by_context || {};
        const selectedDiff = diffSelector ? Number(diffSelector.value || 0) : null;
        const selectedShip = shipSelector ? Number(shipSelector.value || 0) : null;

        // 汇总各难度、各机体的评分数，受另一侧筛选约束
        const diffCounts = new Map();
        const shipCounts = new Map();
        Object.values(contextMap).forEach(ctx => {
            const dId = Number(ctx.difficulty_level_id ?? 0);
            const sId = Number(ctx.ship_type_id ?? 0);
            const cnt = ctx.total_ratings || 0;
            // 统计难度数量时，若已选机体，则仅统计该机体对应的情境
            if (selectedShip === null || selectedShip === sId) {
                diffCounts.set(dId, (diffCounts.get(dId) || 0) + cnt);
            }
            // 统计机体数量时，若已选难度，则仅统计该难度对应的情境
            if (selectedDiff === null || selectedDiff === dId) {
                shipCounts.set(sId, (shipCounts.get(sId) || 0) + cnt);
            }
        });

        // 更新难度下拉
        if (diffSelector) {
            Array.from(diffSelector.options).forEach(opt => {
                if (!opt.dataset.baseLabel) opt.dataset.baseLabel = opt.textContent.split(' (')[0];
                const baseLabel = opt.dataset.baseLabel;
                const id = Number(opt.value || 0);
                const count = diffCounts.get(id) || 0;
                opt.textContent = count > 0 ? `${baseLabel} (${count})` : baseLabel;
            });
        }

        // 更新机体下拉
        if (shipSelector) {
            Array.from(shipSelector.options).forEach(opt => {
                if (!opt.dataset.baseLabel) opt.dataset.baseLabel = opt.textContent.split(' (')[0];
                const baseLabel = opt.dataset.baseLabel;
                const id = Number(opt.value || 0);
                const count = shipCounts.get(id) || 0;
                opt.textContent = count > 0 ? `${baseLabel} (${count})` : baseLabel;
            });
        }
    }

    // --- 5. 修改：页面初始化和表单提交 ---
    // 页面初始化
    if (document.getElementById('qualityChart')) {
        createOrUpdateQualityChart(evaluationData.quality_scores);
    }
    if (diffSelector && shipSelector) {
        diffSelector.addEventListener('change', updateUIForContext);
        shipSelector.addEventListener('change', updateUIForContext);
        // 页面首次加载时，初始化UI
        difficultyDisplay.textContent = evaluationData.overall_difficulty_score > 0 ? evaluationData.overall_difficulty_score.toFixed(2) : '暂无评分';
        updateUIForContext(); // 根据默认选项加载图表
    }
    updateOptionCounts();
    updateUIForContext(); // 初始化时运行一次
    
    // --- 新增：品质评分星级实时显示 ---
    document.querySelectorAll('.star-rating').forEach(ratingContainer => {
        const category = ratingContainer.dataset.category;
        const valueDisplay = ratingContainer.querySelector('.rating-value-display');
        const inputs = ratingContainer.querySelectorAll('input[type="radio"]');
        
        inputs.forEach(input => {
            input.addEventListener('change', () => {
                if (valueDisplay && input.checked) {
                    valueDisplay.textContent = `(${input.value}/10)`;
                }
            });
            input.addEventListener('mouseenter', () => {
                if (!input.checked) {
                    valueDisplay.textContent = `(${input.value}/10)`;
                }
            });
        });
        
        ratingContainer.addEventListener('mouseleave', () => {
            const checked = ratingContainer.querySelector('input:checked');
            if (valueDisplay) {
                valueDisplay.textContent = checked ? `(${checked.value}/10)` : '';
            }
        });
        
        // 初始化显示
        const checked = ratingContainer.querySelector('input:checked');
        if (valueDisplay && checked) {
            valueDisplay.textContent = `(${checked.value}/10)`;
        }
    });
    
    // --- 新增：难度评分滑块和输入框双向同步 ---
    function initDifficultySliders() {
        document.querySelectorAll('.difficulty-slider').forEach(slider => {
            const category = slider.dataset.category;
            const valueInput = document.getElementById(`difficulty-value-${category}`);
            
            if (!valueInput) {
                console.warn(`找不到输入元素: difficulty-value-${category}`);
                return;
            }
            
            // 初始化显示
            valueInput.value = slider.value;
            
            // 滑块变化时更新输入框
            slider.addEventListener('input', function() {
                valueInput.value = this.value;
            });
            
            slider.addEventListener('change', function() {
                valueInput.value = this.value;
            });
            
            // 输入框变化时更新滑块
            valueInput.addEventListener('input', function() {
                let val = parseInt(this.value);
                if (isNaN(val)) return;
                // 限制范围
                if (val < 1) val = 1;
                if (val > 60) val = 60;
                this.value = val;
                slider.value = val;
            });
            
            valueInput.addEventListener('change', function() {
                let val = parseInt(this.value);
                if (isNaN(val)) {
                    this.value = slider.value;
                    return;
                }
                // 限制范围
                if (val < 1) val = 1;
                if (val > 60) val = 60;
                this.value = val;
                slider.value = val;
            });
            
            // 输入框失去焦点时确保值有效
            valueInput.addEventListener('blur', function() {
                let val = parseInt(this.value);
                if (isNaN(val) || val < 1 || val > 60) {
                    this.value = slider.value;
                }
            });
        });
    }
    
    // 初始化滑块
    initDifficultySliders();
    
    // --- 新增：难度评分表单情境选择器联动 ---
    function updateDifficultyFormContext() {
        if (!formDiffSelector || !formShipSelector) return;
        
        const diffId = formDiffSelector.value || '0';
        const shipId = formShipSelector.value || '0';
        const contextKey = `d${diffId}_s${shipId}`;
        
        // 更新显示文本
        const diffText = formDiffSelector.options[formDiffSelector.selectedIndex].text.trim();
        const shipText = formShipSelector.options[formShipSelector.selectedIndex].text.trim();
        if (formContextLabel) {
            formContextLabel.textContent = `${diffText} | ${shipText}`;
        }
        
        // 检查是否有已提交的评分
        if (userRatings.difficulty && userRatings.difficulty[contextKey]) {
            const rating = userRatings.difficulty[contextKey];
            if (difficultyRatingStatus) {
                difficultyRatingStatus.style.display = 'inline-block';
            }
            
            // 填充滑块值（从配置读取维度）
            const difficultyDims = configData.difficulty_dimensions || [];
            for (const dim of difficultyDims) {
                const field = dim.field;
                const name = dim.name;
                if (rating[field] !== null && rating[field] !== undefined) {
                    const slider = document.getElementById(`rating-difficulty-${name}`);
                    const valueInput = document.getElementById(`difficulty-value-${name}`);
                    if (slider && valueInput) {
                        slider.value = rating[field];
                        valueInput.value = rating[field];
                    }
                }
            }
        } else {
            if (difficultyRatingStatus) {
                difficultyRatingStatus.style.display = 'none';
            }
            // 重置滑块
            document.querySelectorAll('.difficulty-slider').forEach(slider => {
                slider.value = 30;
                const category = slider.dataset.category;
                const valueInput = document.getElementById(`difficulty-value-${category}`);
                if (valueInput) {
                    valueInput.value = '30';
                }
            });
        }
    }
    
    if (formDiffSelector && formShipSelector) {
        formDiffSelector.addEventListener('change', updateDifficultyFormContext);
        formShipSelector.addEventListener('change', updateDifficultyFormContext);
        updateDifficultyFormContext(); // 初始化
        // 重新初始化滑块（因为可能动态加载了新的值）
        initDifficultySliders();
    }
    
    // 主题切换时重绘图表
    document.addEventListener('themeChanged', () => {
        if (document.getElementById('qualityChart')) {
            createOrUpdateQualityChart(evaluationData.quality_scores);
        }
        updateUIForContext();
    });

    // 评分表单提交逻辑
    const setupRatingForm = (formId, successCallback) => {
        const form = document.getElementById(formId);
        if (form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                const submitButton = form.querySelector('button[type="submit"]');
                submitButton.setAttribute('aria-busy', 'true');
                
                const formData = new FormData(form);
                
                // 对于难度评分，确保滑块和输入框值一致（表单字段名已经在模板中使用字段名）
                if (formId === 'difficulty-rating-form') {
                    document.querySelectorAll('.difficulty-value-input').forEach(input => {
                        const category = input.dataset.category;
                        const field = input.dataset.field;
                        const slider = document.getElementById(`rating-difficulty-${category}`);
                        if (slider && input.value) {
                            // 确保滑块和输入框值一致
                            slider.value = input.value;
                            // 表单字段名已经在模板中使用字段名（rating_{{field}}），不需要再次设置
                        }
                    });
                }
                
                const actionUrl = form.getAttribute('action');
                try {
                    const response = await fetch(actionUrl, { method: 'POST', body: formData });
                    const result = await response.json();
                    if (!response.ok) throw new Error(result.detail || '未知错误');
                    
                    showToast(result.message);
                    if (successCallback) successCallback(result);

                } catch (error) {
                    showToast(`提交失败: ${error.message}`, true);
                } finally {
                    submitButton.removeAttribute('aria-busy', 'false');
                    // 不自动清空表单，保留用户输入以便查看
                }
            });
        }
    };
    // 成功提交品质评分后的回调函数
    function onQualitySubmitSuccess(result) {
        // 更新全局数据
        evaluationData.quality_scores = result.updated_scores;
        evaluationData.overall_quality_score = result.overall_score;
        // 更新用户评分数据
        const form = document.getElementById('quality-rating-form');
        if (form) {
            const qualityMap = {
                '趣味性': 'fun',
                '核心设计': 'core',
                '深度': 'depth',
                '演出': 'performance',
                '剧情': 'story'
            };
            if (!userRatings.quality) userRatings.quality = {};
            Object.keys(qualityMap).forEach(cat => {
                const input = form.querySelector(`input[name="rating_${cat}"]:checked`);
                if (input) {
                    userRatings.quality[qualityMap[cat]] = parseInt(input.value);
                }
            });
        }
        // 更新UI
        createOrUpdateQualityChart(result.updated_scores);
        if (qualityDisplay) qualityDisplay.textContent = result.overall_score.toFixed(2);
    }
    
    // 成功提交难度评分后的回调函数
    function onDifficultySubmitSuccess(result) {
        // 更新全局数据
        evaluationData.difficulty_scores_by_context[result.updated_context_key] = result.updated_context_data;
        // 更新用户评分数据
        if (!userRatings.difficulty) userRatings.difficulty = {};
        const contextKey = result.updated_context_key;
        // 从表单获取提交的值（从配置读取维度）
        const difficultyDims = configData.difficulty_dimensions || [];
        const ratingData = {};
        for (const dim of difficultyDims) {
            const field = dim.field;
            const name = dim.name;
            const value = document.getElementById(`rating-difficulty-${name}`)?.value;
            ratingData[field] = value ? parseInt(value) : null;
        }
        userRatings.difficulty[contextKey] = ratingData;
        // 重新渲染当前查看的情境，数据已经是新的了
        updateUIForContext();
        updateDifficultyFormContext();
    }
    setupRatingForm('quality-rating-form', onQualitySubmitSuccess);
    setupRatingForm('difficulty-rating-form', onDifficultySubmitSuccess);

    // --- 撤销评分按钮 ---
    const deleteQualityBtn = document.getElementById('delete-quality-rating-btn');
    if (deleteQualityBtn) {
        deleteQualityBtn.addEventListener('click', async () => {
            if (!confirm('确定要撤销你的品质评分吗？')) return;
            try {
                const response = await fetch(`/game/${gameId}/rate_quality`, {
                    method: 'DELETE'
                });
                const result = await response.json();
                if (!response.ok) {
                    throw new Error(result.detail || '撤销失败');
                }
                showToast(result.message || '已撤销你的品质评分。');
                window.location.reload();
            } catch (err) {
                showToast(`撤销失败: ${err.message}`, true);
            }
        });
    }

    const deleteDifficultyBtn = document.getElementById('delete-difficulty-rating-btn');
    if (deleteDifficultyBtn && formDiffSelector && formShipSelector) {
        deleteDifficultyBtn.addEventListener('click', async () => {
            const diffId = formDiffSelector.value;
            const shipId = formShipSelector.value;
            if (!confirm('确定要撤销当前情境下你的难度评分吗？')) return;

            const params = new URLSearchParams();
            if (diffId) params.set('difficulty_level_id', diffId);
            if (shipId) params.set('ship_type_id', shipId);

            try {
                const response = await fetch(`/game/${gameId}/rate_difficulty?${params.toString()}`, {
                    method: 'DELETE'
                });
                const result = await response.json();
                if (!response.ok) {
                    throw new Error(result.detail || '撤销失败');
                }
                showToast(result.message || '已撤销当前情境的难度评分。');
                window.location.reload();
            } catch (err) {
                showToast(`撤销失败: ${err.message}`, true);
            }
        });
    }
    
    // --- 6. 您的评论和删除游戏逻辑 (保留) ---
    // --- Comment Form Submission (for NEW comments) ---
	const commentForm = document.getElementById('comment-form');
	if (commentForm) {
		commentForm.addEventListener('submit', async function(event) {
			event.preventDefault();
			const formData = new FormData(commentForm);
			const gameId = commentForm.dataset.gameId;
			const submitButton = commentForm.querySelector('button[type="submit"]');

			submitButton.setAttribute('aria-busy', 'true');

			try {
				const response = await fetch(`/api/v1/games/${gameId}/comments`, {
					method: 'POST',
					body: formData
				});

				if (response.status === 401) {
					throw new Error('请先登录再发表评论。');
				}
				
				const result = await response.json();

				if (!response.ok) {
					throw new Error(result.detail || '未知错误');
				}

				if (result.status === 'success') {
					showToast("评论已发表！");
					addCommentToDOM(result.comment); // 调用下面的辅助函数动态添加
					commentForm.reset();
				}
			} catch (error) {
				showToast(`评论失败: ${error.message}`, true);
			} finally {
				submitButton.removeAttribute('aria-busy');
			}
		});
	}

    // =======================================================================
	//   评论管理逻辑 (编辑、删除、动态添加)
	// =======================================================================

	/**
	 * A utility function to prevent XSS attacks by escaping HTML content.
	 * @param {string} str The string to escape.
	 * @returns {string} The escaped string.
	 */
	function escapeHTML(str) {
		if (str === null || str === undefined) return '';
		const p = document.createElement('p');
		p.textContent = str;
		return p.innerHTML;
	}

	/**
	 * Creates a complete blockquote element for a comment based on its data and user permissions.
	 * @param {object} comment - The comment object {id, content, user_name, user_id}.
	 * @returns {HTMLElement} The created blockquote element.
	 */
	function createCommentElement(comment) {
		const sessionData = JSON.parse(document.getElementById('session-data').textContent);
		const isAdmin = window.IS_ADMIN || false;
		const sessionUserId = sessionData.user_id;

		const isAuthor = comment.user_id === sessionUserId;
		const canDelete = isAuthor || isAdmin;
		const canEdit = isAuthor;

		let actionsHTML = '';
		// 只有在可以编辑或可以删除时，才创建span容器
		if (canEdit || canDelete) {
			actionsHTML += '<span class="comment-actions">';
			
			// 只有作者能看到编辑按钮
			if (canEdit) {
				actionsHTML += `<a href="#" class="edit-comment" data-comment-id="${comment.id}">编辑</a>`;
			}

			// 如果作者同时也是可删除者（即作者本人），且管理员也能删除，需要一个分隔符
			if (canEdit && canDelete) {
				 actionsHTML += ' | ';
			}
			
			// 作者和管理员都能看到删除按钮
			if (canDelete) {
				actionsHTML += `<a href="#" class="delete-comment" data-comment-id="${comment.id}">删除</a>`;
			}
			actionsHTML += '</span>';
		}

		const blockquote = document.createElement('blockquote');
		blockquote.dataset.commentId = comment.id;

		// 构建内部HTML，使用flex布局的footer
		const userNameLink = comment.user_id 
			? `<a href="/user/${comment.user_id}">${escapeHTML(comment.user_name)}</a>`
			: escapeHTML(comment.user_name);
		blockquote.innerHTML = `
			<p>${escapeHTML(comment.content)}</p>
			<footer>
				<cite>- ${userNameLink}</cite>
				${actionsHTML}
			</footer>
		`;
		return blockquote;
	}

	/**
	 * Dynamically adds a new comment to the top of the comments section.
	 * @param {object} comment - The new comment object.
	 */
	function addCommentToDOM(comment) {
		const commentsSection = document.getElementById('comments-section');
		const newCommentElement = createCommentElement(comment);
		
		document.getElementById('no-comments-placeholder')?.remove();
		commentsSection.prepend(newCommentElement);
	}

	/**
	 * Main event handler for all clicks within the comments section (edit, delete, cancel).
	 * This uses event delegation for efficiency.
	 */
	document.getElementById('comments-section').addEventListener('click', async function(event) {
		const target = event.target;
		
		// --- Handle CLICK on "Delete" link ---
		if (target.classList.contains('delete-comment')) {
			event.preventDefault();
			const commentId = target.dataset.commentId;
			if (!confirm('你确定要删除这条评论吗？')) return;

			try {
				const response = await fetch(`/api/v1/comments/${commentId}`, { method: 'DELETE' });

				if (response.ok) { // Handles 204 No Content success
					showToast('评论已删除。');
					const blockquote = target.closest('blockquote');
					blockquote.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
					blockquote.style.opacity = '0';
					blockquote.style.transform = 'translateX(-20px)';
					setTimeout(() => blockquote.remove(), 500);
				} else {
					const result = await response.json();
					throw new Error(result.detail || '删除失败');
				}
			} catch (err) {
				showToast(`删除失败: ${err.message}`, true);
			}
		}

		// --- Handle CLICK on "Edit" link ---
		if (target.classList.contains('edit-comment')) {
			event.preventDefault();
			const blockquote = target.closest('blockquote');
			const p = blockquote.querySelector('p');
			const currentContent = p.textContent;
			
			blockquote.innerHTML = `
				<form class="edit-comment-form" data-comment-id="${blockquote.dataset.commentId}">
					<textarea name="content" required rows="3">${escapeHTML(currentContent)}</textarea>
					<div class="grid" style="margin-top: 0.5rem;">
						<button type="submit">保存更改</button>
						<button type="button" class="cancel-edit secondary outline">取消</button>
					</div>
				</form>
			`;
			blockquote.querySelector('textarea').focus();
		}

		// --- Handle CLICK on "Cancel Edit" button ---
		if (target.classList.contains('cancel-edit')) {
			event.preventDefault();
			window.location.reload(); // Reloading is the simplest way to cancel
		}
	});

	/**
	 * Event handler for submitting the EDIT comment form.
	 * This also uses event delegation.
	 */
	document.getElementById('comments-section').addEventListener('submit', async function(event){
		if (event.target.classList.contains('edit-comment-form')) {
			event.preventDefault();
			const form = event.target;
			const commentId = form.dataset.commentId;
			const content = form.querySelector('textarea').value;
			const submitButton = form.querySelector('button[type="submit"]');

			submitButton.setAttribute('aria-busy', 'true');

			try {
				const response = await fetch(`/api/v1/comments/${commentId}`, {
					method: 'PUT',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ content: content })
				});
				
				const result = await response.json();

				if (!response.ok) {
					throw new Error(result.detail || '更新失败');
				}

				showToast('评论已更新！');
				const updatedCommentElement = createCommentElement(result.comment);
				form.closest('blockquote').replaceWith(updatedCommentElement);

			} catch (err) {
				showToast(`更新失败: ${err.message}`, true);
			} finally {
				submitButton.removeAttribute('aria-busy');
			}
		}
	});
    
    // +++ 新增删除游戏的处理逻辑 +++
	const deleteGameButton = document.getElementById('delete-game-button');
	if (deleteGameButton) {
		deleteGameButton.addEventListener('click', async (e) => {
			const button = e.currentTarget;
			const gameId = button.dataset.gameId;
			const gameTitle = button.dataset.gameTitle;

			// 弹出两次确认框，增加安全性
			const confirmation1 = prompt(`这是一个危险操作！\n要删除游戏 "${gameTitle}"，请输入它的名字进行确认:`);
			if (confirmation1 !== gameTitle) {
				showToast('名称输入错误，删除操作已取消。', true);
				return;
			}

			const confirmation2 = confirm(`最后确认：真的要永久删除 "${gameTitle}" 吗？此操作无法撤销！`);
			if (!confirmation2) {
				showToast('删除操作已取消。');
				return;
			}

			// 发送删除请求
			try {
				const response = await fetch(`/admin/game/${gameId}`, {
					method: 'DELETE'
				});

				const result = await response.json();

				if (!response.ok) {
					throw new Error(result.detail || '删除失败');
				}

				alert(result.message); // 使用 alert 进行强提醒
				window.location.href = '/games'; // 删除成功后跳转到游戏列表页

			} catch (error) {
				console.error('删除游戏时出错:', error);
				showToast(`删除失败: ${error.message}`, true);
			}
		});
	}
	// +++ 新增：JS版本的境界计算函数（从配置读取） +++
	function getDifficultyRealmJS(score) {
		const realms = configData.difficulty_realms || [];
		if (!realms.length) {
			// 如果没有配置，返回N/A
			return "N/A";
		}
		
		if (score <= 0) {
			// 查找threshold为0的段位
			const zeroRealm = realms.find(r => r.threshold === 0);
			return zeroRealm ? zeroRealm.name : "N/A";
		}
		
		// 按threshold从大到小排序（排除null）
		const sortedRealms = realms
			.filter(r => r.threshold !== null && r.threshold !== undefined)
			.sort((a, b) => b.threshold - a.threshold);
		
		// 查找匹配的段位
		for (const realm of sortedRealms) {
			if (score > realm.threshold) {
				return realm.name;
			}
		}
		
		// 如果所有段位都不匹配，返回最后一个（通常是threshold为null的段位）
		if (realms.length > 0) {
			return realms[realms.length - 1].name;
		}
		
		return "N/A";
	}
    // 确保图标被渲染
    if (window.lucide) {
        lucide.createIcons();
    }
});