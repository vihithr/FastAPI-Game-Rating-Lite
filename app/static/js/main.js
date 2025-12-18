document.addEventListener('DOMContentLoaded', () => {
    lucide.createIcons();

    // --- Global Variables & Initial Data ---
    const gameData = JSON.parse(document.getElementById('evaluation-data').textContent);
    const sessionData = JSON.parse(document.getElementById('session-data').textContent);
    const gameId = document.getElementById('comment-form')?.dataset.gameId;
    let qualityChart, difficultyChart;

    // --- Toast Notification ---
    const toast = document.getElementById('toast-notification');
    function showToast(message, isError = false) {
        toast.textContent = message;
        toast.style.backgroundColor = isError ? 'var(--pico-color-red-500)' : 'var(--pico-contrast)';
        toast.classList.add('show');
        setTimeout(() => { toast.classList.remove('show'); }, 3000);
    }

    // --- Username Persistence ---
    const usernameInputs = [
        document.getElementById('user_name_rating_quality'),
        document.getElementById('user_name_rating_difficulty'),
        document.getElementById('user_name_comment')
    ];
    const savedUsername = localStorage.getItem('stg_username');
    if (savedUsername) {
        usernameInputs.forEach(input => { if(input) input.value = savedUsername; });
    }
    const saveUsername = (name) => {
        if (name && name.trim() !== '') {
            localStorage.setItem('stg_username', name.trim());
        }
    };
    
    // --- Chart.js Initialization ---
    if(window.ChartDataLabels) {
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

    // Difficulty Rating Chart Function
    function createOrUpdateDifficultyChart(scores) {
        const ctx = document.getElementById('difficultyChart').getContext('2d');
        if (difficultyChart) difficultyChart.destroy();

        const labels = scores.map(s => s.category);
        const data = scores.map(s => s.raw_value);

        const isDarkMode = document.documentElement.dataset.theme === 'dark';
        const gridColor = isDarkMode ? 'rgba(255, 255, 255, 0.15)' : 'rgba(0, 0, 0, 0.1)';
        const labelColor = isDarkMode ? 'rgba(255, 255, 255, 0.9)' : 'rgba(0, 0, 0, 0.8)';
        const realmTooltips = scores.map(s => s.value);
        
        const difficultyGradient = ctx.createLinearGradient(0, 0, 0, ctx.canvas.height);
        difficultyGradient.addColorStop(0, 'rgba(255, 99, 132, 0.6)');
        difficultyGradient.addColorStop(1, 'rgba(255, 99, 132, 0.1)');
        const difficultyBorderColor = 'rgb(255, 99, 132)';

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
                        beginAtZero: true, max: 60,
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
    
    // --- Initial chart draw & Event Listener for Theme Change ---
    if (document.getElementById('qualityChart')) {
        createOrUpdateQualityChart(gameData.quality_scores);
    }
    if (document.getElementById('difficultyChart')) {
        createOrUpdateDifficultyChart(gameData.difficulty_scores);
    }
    document.addEventListener('themeChanged', () => {
		const currentEvaluationData = JSON.parse(document.getElementById('evaluation-data').textContent);
		if (document.getElementById('qualityChart')) {
			createOrUpdateQualityChart(currentEvaluationData.quality_scores);
		}
		if (document.getElementById('difficultyChart')) {
			createOrUpdateDifficultyChart(currentEvaluationData.difficulty_scores);
		}
	});

    // --- Form Submission Logic ---
    async function handleRatingFormSubmit(event, form, chartUpdater, scoreType) {
        event.preventDefault();
        const formData = new FormData(form);
        const actionUrl = form.getAttribute('action');
        const userName = formData.get('user_name') || '匿名玩家';
        
        try {
            const response = await fetch(actionUrl, { method: 'POST', body: formData });
            const result = await response.json();

            if (!response.ok) {
                showToast(`评分失败: ${result.detail || '未知错误'}`, true);
                return;
            }
            
            saveUsername(userName);
            showToast(result.message);
            
            if (result.status === 'success' && result.updated_scores) {
                if (scoreType === 'quality') {
                    gameData.quality_scores = result.updated_scores;
                } else if (scoreType === 'difficulty') {
                    gameData.difficulty_scores = result.updated_scores;
                }
                chartUpdater(result.updated_scores);
            }
        } catch (error) {
            console.error(`Error submitting ${scoreType} rating:`, error);
            showToast('提交失败，请检查网络或联系管理员。', true);
        }
    }

    const qualityForm = document.getElementById('quality-rating-form');
    if (qualityForm) {
        qualityForm.addEventListener('submit', (e) => handleRatingFormSubmit(e, qualityForm, createOrUpdateQualityChart, 'quality'));
    }

    const difficultyForm = document.getElementById('difficulty-rating-form');
    if (difficultyForm) {
        difficultyForm.addEventListener('submit', (e) => handleRatingFormSubmit(e, difficultyForm, createOrUpdateDifficultyChart, 'difficulty'));
    }

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
});