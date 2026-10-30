// /app/static/js/game-details.js — demo layout + real data/API
document.addEventListener('DOMContentLoaded', () => {
    'use strict';

    const evaluationEl = document.getElementById('evaluation-data');
    if (!evaluationEl) return;

    const evaluation = JSON.parse(evaluationEl.textContent);
    const userRatingsEl = document.getElementById('user-ratings-data');
    const userRatings = userRatingsEl ? JSON.parse(userRatingsEl.textContent) : { quality: null, difficulty: {} };
    const sessionEl = document.getElementById('session-data');
    const session = sessionEl ? JSON.parse(sessionEl.textContent) : { user_id: null, username: null, is_admin: false };
    const page = document.querySelector('.detail-demo');
    const gameId = page ? page.dataset.gameId : null;
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const toastEl = document.getElementById('demo-toast');
    function toast(message) {
        if (!toastEl) return;
        toastEl.textContent = message;
        toastEl.classList.add('is-visible');
        window.clearTimeout(toast._timer);
        toast._timer = window.setTimeout(() => toastEl.classList.remove('is-visible'), 2600);
    }

    function scrollToElement(el) {
        if (!el) return;
        el.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    }

    function average(values) {
        return values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0;
    }

    function getRealm(score) {
        if (!score || score <= 0) return '暂无评分';
        if (score <= 5) return '见习一';
        if (score <= 10) return '见习二';
        if (score <= 15) return '新手一';
        if (score <= 20) return '新手二';
        if (score <= 25) return '入门一';
        if (score <= 30) return '入门二';
        if (score <= 35) return '进阶一';
        if (score <= 40) return '进阶二';
        if (score <= 45) return '上级一';
        if (score <= 50) return '上级二';
        if (score <= 55) return '上级三';
        return '论外';
    }

    function escapeHTML(value) {
        const p = document.createElement('p');
        p.textContent = value == null ? '' : String(value);
        return p.innerHTML;
    }

    /* ---------- Quality radar ---------- */
    const qualityDimensions = (evaluation.quality_scores || []).map((item) => ({
        label: item.category,
        value: Number(item.raw_value) || 0,
        count: Number(item.count) || 0
    }));
    const qualityHasData = qualityDimensions.some((item) => item.count > 0);

    function renderQualityRadar() {
        const svg = document.getElementById('quality-radar');
        if (!svg) return;
        // 无数据时不画数据面，但保留网格与维度标签，避免整块空白；
        // 同时给外层打标记，隐藏居中的 .radar-average，否则会和中心文字叠在一起
        if (!qualityHasData) {
            const wrap = svg.closest('.radar-wrap');
            if (wrap) wrap.classList.add('is-empty');
        }
        const size = 260;
        const cx = size / 2;
        const cy = size / 2;
        const radius = 84;
        const count = qualityDimensions.length;
        const angle = (i) => (-90 + (360 / count) * i) * Math.PI / 180;
        const point = (i, r) => [cx + Math.cos(angle(i)) * r, cy + Math.sin(angle(i)) * r];
        const points = (r) => qualityDimensions.map((_, i) => point(i, r).map((n) => n.toFixed(1)).join(',')).join(' ');

        let html = '<g class="radar-grid">';
        [0.25, 0.5, 0.75, 1].forEach((ratio) => {
            html += '<polygon points="' + points(radius * ratio) + '"></polygon>';
        });
        qualityDimensions.forEach((_, i) => {
            const end = point(i, radius);
            html += '<line x1="' + cx + '" y1="' + cy + '" x2="' + end[0].toFixed(1) + '" y2="' + end[1].toFixed(1) + '"></line>';
        });
        html += '</g>';

        if (qualityHasData) {
            html += '<polygon class="radar-area" points="' + qualityDimensions.map((item, i) => {
                return point(i, radius * item.value / 10).map((n) => n.toFixed(1)).join(',');
            }).join(' ') + '"></polygon>';

            html += '<g class="radar-dots">';
            qualityDimensions.forEach((item, i) => {
                const p = point(i, radius * item.value / 10);
                html += '<circle cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) + '" r="3.6"></circle>';
            });
            html += '</g>';
        }

        qualityDimensions.forEach((item, i) => {
            const p = point(i, radius + 26);
            const anchor = Math.abs(p[0] - cx) < 6 ? 'middle' : (p[0] > cx ? 'start' : 'end');
            html += '<text class="radar-label" x="' + p[0].toFixed(1) + '" y="' + (p[1] + 3.5).toFixed(1) + '" text-anchor="' + anchor + '">' + escapeHTML(item.label) + '</text>';
        });

        if (!qualityHasData) {
            html += '<text x="' + cx + '" y="' + (cy + 4) + '" text-anchor="middle" class="radar-label">暂无细分评分</text>';
        }

        svg.innerHTML = html;
    }

    renderQualityRadar();

    /* ---------- Difficulty contexts ---------- */
    const contexts = evaluation.difficulty_scores_by_context || {};
    const difficultyState = { level: '0', ship: '0' };
    const levelButtons = Array.prototype.slice.call(document.querySelectorAll('.segmented [data-level]'));
    const shipFilter = document.getElementById('ship-filter');
    const dimensionKeys = ['dodge', 'strategy', 'execution'];

    function currentContextKey() {
        return 'd' + difficultyState.level + '_s' + difficultyState.ship;
    }

    function selectedLevelLabel() {
        const button = levelButtons.find((item) => item.dataset.level === difficultyState.level);
        if (!button) return '游戏总体';
        return (button.childNodes[0].textContent || '').trim() || '游戏总体';
    }

    function selectedShipLabel() {
        if (!shipFilter) return '全机体/角色';
        const option = shipFilter.options[shipFilter.selectedIndex];
        return option ? option.textContent.trim() : '全机体/角色';
    }

    function renderDifficulty() {
        const context = contexts[currentContextKey()];
        const categories = context ? context.categories : [];
        dimensionKeys.forEach((key, index) => {
            const row = document.querySelector('.diff-row[data-dim="' + key + '"]');
            if (!row) return;
            const data = categories[index];
            const strong = row.querySelector('.diff-row__value strong');
            const small = row.querySelector('.diff-row__value small');
            const fill = row.querySelector('.bar-fill');
            if (data && data.count > 0) {
                strong.textContent = Number(data.raw_value).toFixed(1);
                small.textContent = String(data.value).split(' ')[0];
                fill.style.setProperty('--v', Math.max(0, Math.min(100, data.raw_value / 60 * 100)) + '%');
            } else {
                strong.textContent = '—';
                small.textContent = '暂无';
                fill.style.setProperty('--v', '0%');
            }
        });

        const realmName = document.getElementById('realm-name');
        const realmScore = document.getElementById('realm-score');
        const realmMeta = document.getElementById('realm-meta');
        const realmMarker = document.getElementById('realm-marker');
        const heroRealm = document.getElementById('hero-realm');
        const heroDifficulty = document.getElementById('hero-difficulty');
        const heroMeta = document.getElementById('hero-difficulty-meta');
        const heroMarker = document.getElementById('hero-gauge-marker');
        const count = context ? Number(context.total_ratings || 0) : 0;

        if (context && count > 0) {
            const overall = Number(context.overall_avg) || 0;
            const realm = getRealm(overall);
            if (realmName) realmName.textContent = realm;
            if (realmScore) realmScore.textContent = overall.toFixed(1);
            if (realmMeta) realmMeta.textContent = selectedLevelLabel() + ' · ' + selectedShipLabel() + ' · ' + count + ' 条记录';
            if (realmMarker) realmMarker.style.left = (overall / 60 * 100) + '%';
            if (heroRealm) heroRealm.textContent = realm;
            if (heroDifficulty) heroDifficulty.textContent = overall.toFixed(1);
            if (heroMeta) heroMeta.textContent = count + ' 条难度记录 · ' + selectedLevelLabel();
            if (heroMarker) heroMarker.style.left = (overall / 60 * 100) + '%';
        } else {
            if (realmName) realmName.textContent = '暂无评分';
            if (realmScore) realmScore.textContent = '—';
            if (realmMeta) realmMeta.textContent = selectedLevelLabel() + ' · ' + selectedShipLabel() + ' · 还没有记录';
            if (realmMarker) realmMarker.style.left = '0%';
            if (heroRealm) heroRealm.textContent = '暂无';
            if (heroDifficulty) heroDifficulty.textContent = '—';
            if (heroMeta) heroMeta.textContent = '当前情境还没有难度记录';
            if (heroMarker) heroMarker.style.left = '0%';
        }

        levelButtons.forEach((button) => {
            const active = button.dataset.level === difficultyState.level;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-selected', String(active));
        });
    }

    levelButtons.forEach((button) => {
        button.addEventListener('click', () => {
            difficultyState.level = button.dataset.level;
            renderDifficulty();
        });
    });
    if (shipFilter) {
        shipFilter.addEventListener('change', () => {
            difficultyState.ship = shipFilter.value;
            renderDifficulty();
        });
    }
    renderDifficulty();

    /* ---------- Section nav / scroll spy ---------- */
    const sectionLinks = Array.prototype.slice.call(document.querySelectorAll('.detail-tabs__links a'));
    const sections = sectionLinks.map((link) => document.querySelector(link.getAttribute('href'))).filter(Boolean);

    function updateSectionNav() {
        if (!sections.length) return;
        let active = sections[0];
        const threshold = 140;
        sections.forEach((section) => {
            if (section.getBoundingClientRect().top <= threshold) active = section;
        });
        sectionLinks.forEach((link) => {
            link.classList.toggle('is-active', link.getAttribute('href') === '#' + active.id);
        });
    }
    window.addEventListener('scroll', updateSectionNav, { passive: true });
    updateSectionNav();

    /* ---------- Reviews ---------- */
    const reviewList = document.getElementById('review-list');
    const reviewForm = document.getElementById('comment-form');
    const reviewContent = document.getElementById('review-content');
    const reviewCount = document.getElementById('review-count');
    const reviewSubmit = reviewForm ? reviewForm.querySelector('button[type="submit"]') : null;
    const reviewCountTab = document.getElementById('review-count-tab');

    function updateReviewForm() {
        if (!reviewContent || !reviewSubmit || !reviewCount) return;
        const length = reviewContent.value.length;
        reviewCount.textContent = length + ' / 2000';
        reviewSubmit.disabled = reviewContent.value.trim().length === 0;
    }
    if (reviewContent) {
        reviewContent.addEventListener('input', updateReviewForm);
        updateReviewForm();
    }

    function updateReviewCount() {
        if (!reviewList) return;
        const count = reviewList.querySelectorAll('.review').length;
        if (reviewCountTab) reviewCountTab.textContent = String(count);
        const empty = reviewList.querySelector('.home-empty-panel');
        if (count > 0 && empty) empty.remove();
    }

    function createReviewElement(comment) {
        const article = document.createElement('article');
        article.className = 'review';
        article.dataset.commentId = String(comment.id);

        const avatar = document.createElement('span');
        avatar.className = 'review__avatar';
        avatar.style.setProperty('--hue', String((Number(comment.id) * 47) % 360));
        avatar.setAttribute('aria-hidden', 'true');
        avatar.textContent = (comment.user_name || '匿').slice(0, 1);

        const body = document.createElement('div');
        body.className = 'review__body';
        const head = document.createElement('div');
        head.className = 'review__head';
        const name = document.createElement('strong');
        if (comment.user_id) {
            const link = document.createElement('a');
            link.href = '/user/' + comment.user_id;
            link.textContent = comment.user_name || '匿名玩家';
            name.appendChild(link);
        } else {
            name.textContent = comment.user_name || '匿名玩家';
        }
        const meta = document.createElement('span');
        meta.className = 'review__meta';
        meta.textContent = '社区评论';
        head.append(name, meta);

        const content = document.createElement('p');
        content.className = 'review__content';
        content.textContent = comment.content;

        const foot = document.createElement('div');
        foot.className = 'review__foot';
        const idMeta = document.createElement('span');
        idMeta.className = 'review__meta';
        idMeta.textContent = '评论 #' + comment.id;
        foot.appendChild(idMeta);
        if (session.user_id && (Number(comment.user_id) === Number(session.user_id) || session.is_admin)) {
            const actions = document.createElement('span');
            actions.className = 'review__actions';
            const edit = document.createElement('button');
            edit.type = 'button';
            edit.className = 'link-button edit-comment';
            edit.dataset.commentId = String(comment.id);
            edit.textContent = '编辑';
            const remove = document.createElement('button');
            remove.type = 'button';
            remove.className = 'link-button delete-comment';
            remove.dataset.commentId = String(comment.id);
            remove.textContent = '删除';
            actions.append(edit, remove);
            foot.appendChild(actions);
        }

        body.append(head, content, foot);
        article.append(avatar, body);
        return article;
    }

    if (reviewForm) {
        reviewForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            const text = reviewContent.value.trim();
            if (!text) return;
            reviewSubmit.setAttribute('aria-busy', 'true');
            try {
                const formData = new FormData();
                formData.set('content', text);
                const response = await fetch('/api/v1/games/' + gameId + '/comments', {
                    method: 'POST',
                    body: formData
                });
                if (response.status === 401) {
                    window.location.href = '/login?redirect=' + encodeURIComponent(window.location.pathname);
                    return;
                }
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || '发表失败');
                const empty = reviewList ? reviewList.querySelector('.home-empty-panel') : null;
                if (empty) empty.remove();
                if (reviewList) reviewList.prepend(createReviewElement(result.comment));
                reviewContent.value = '';
                updateReviewForm();
                updateReviewCount();
                toast('评论已发表');
                if (window.lucide) window.lucide.createIcons();
            } catch (error) {
                toast('发表失败：' + error.message);
            } finally {
                reviewSubmit.removeAttribute('aria-busy');
            }
        });
    }

    if (reviewList) {
        reviewList.addEventListener('click', async (event) => {
            const editButton = event.target.closest('.edit-comment');
            const deleteButton = event.target.closest('.delete-comment');
            if (!editButton && !deleteButton) return;
            const review = event.target.closest('.review');
            if (!review) return;
            const id = review.dataset.commentId;

            if (deleteButton) {
                if (!confirm('确定要删除这条评论吗？')) return;
                try {
                    const response = await fetch('/api/v1/comments/' + id, { method: 'DELETE' });
                    if (!response.ok && response.status !== 204) {
                        const result = await response.json();
                        throw new Error(result.detail || '删除失败');
                    }
                    review.remove();
                    updateReviewCount();
                    toast('评论已删除');
                } catch (error) {
                    toast('删除失败：' + error.message);
                }
                return;
            }

            const content = review.querySelector('.review__content');
            if (!content || review.querySelector('.review-edit')) return;
            const original = content.textContent;
            const editor = document.createElement('div');
            editor.className = 'review-edit';
            const textarea = document.createElement('textarea');
            textarea.value = original;
            textarea.maxLength = 2000;
            const actions = document.createElement('div');
            actions.className = 'review-edit__actions';
            const save = document.createElement('button');
            save.type = 'button';
            save.className = 'demo-btn demo-btn--primary';
            save.textContent = '保存';
            const cancel = document.createElement('button');
            cancel.type = 'button';
            cancel.className = 'demo-btn demo-btn--ghost';
            cancel.textContent = '取消';
            actions.append(save, cancel);
            editor.append(textarea, actions);
            content.hidden = true;
            content.after(editor);
            textarea.focus();

            cancel.addEventListener('click', () => {
                editor.remove();
                content.hidden = false;
            });
            save.addEventListener('click', async () => {
                const text = textarea.value.trim();
                if (!text) return;
                try {
                    const response = await fetch('/api/v1/comments/' + id, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ content: text })
                    });
                    const result = await response.json();
                    if (!response.ok) throw new Error(result.detail || '保存失败');
                    content.textContent = result.comment ? result.comment.content : text;
                    editor.remove();
                    content.hidden = false;
                    toast('评论已更新');
                } catch (error) {
                    toast('保存失败：' + error.message);
                }
            });
        });
    }

    const reviewSortButtons = Array.prototype.slice.call(document.querySelectorAll('[data-sort]'));
    reviewSortButtons.forEach((button) => {
        button.addEventListener('click', () => {
            if (!reviewList) return;
            reviewSortButtons.forEach((item) => item.classList.toggle('is-active', item === button));
            const reviews = Array.prototype.slice.call(reviewList.querySelectorAll('.review'));
            reviews.sort((a, b) => {
                const diff = Number(a.dataset.commentId) - Number(b.dataset.commentId);
                return button.dataset.sort === 'oldest' ? diff : -diff;
            });
            reviews.forEach((review) => reviewList.appendChild(review));
        });
    });

    /* ---------- Share / shortcuts ---------- */
    const shareButton = document.querySelector('[data-share]');
    if (shareButton) {
        shareButton.addEventListener('click', () => {
            const done = () => toast('页面链接已复制');
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(window.location.href).then(done).catch(() => toast('当前环境无法复制链接'));
            } else {
                toast('当前环境无法复制链接');
            }
        });
    }

    document.querySelectorAll('[data-write-review]').forEach((button) => {
        button.addEventListener('click', () => {
            const section = document.getElementById('reviews');
            scrollToElement(section);
            if (reviewContent) {
                window.setTimeout(() => reviewContent.focus({ preventScroll: true }), reduceMotion ? 0 : 380);
            }
        });
    });

    /* ---------- Slider factory ---------- */
    function createDemoSlider(root, options) {
        if (!root) return null;
        const track = root.querySelector('.demo-slider__track');
        const fill = root.querySelector('.demo-slider__fill');
        const thumb = root.querySelector('.demo-slider__thumb');
        const min = Number(root.dataset.min);
        const max = Number(root.dataset.max);
        const stepSize = Number(root.dataset.step) || 1;
        const decimals = (String(stepSize).split('.')[1] || '').length;
        const initial = options && options.value !== undefined
            ? options.value
            : (root.dataset.value !== undefined ? root.dataset.value : (root.getAttribute('aria-valuenow') || min));
        let value = Number(initial);
        let dragging = false;
        let trackLeft = 0;
        let trackWidth = 0;

        const clamp = (v) => Math.min(max, Math.max(min, v));
        const quantize = (raw) => {
            const snapped = min + Math.round((clamp(Number(raw)) - min) / stepSize) * stepSize;
            return Number(clamp(snapped).toFixed(decimals));
        };
        function measure() {
            const rect = track.getBoundingClientRect();
            trackLeft = rect.left;
            trackWidth = Math.max(0, rect.width);
        }
        function render(v) {
            const fraction = (v - min) / (max - min);
            if (fill) fill.style.transform = 'scaleX(' + fraction.toFixed(4) + ')';
            if (thumb) thumb.style.transform = 'translate3d(' + (fraction * trackWidth).toFixed(2) + 'px, -50%, 0)';
            root.setAttribute('aria-valuenow', decimals ? v.toFixed(decimals) : String(v));
        }
        function setValue(raw, source) {
            const next = quantize(raw);
            if (next === value && source !== 'init') return value;
            value = next;
            render(value);
            if (source !== 'init' && options && options.onInput) options.onInput(value);
            return value;
        }
        function refresh() {
            measure();
            if (trackWidth > 0) render(value);
        }
        function endDrag(event) {
            if (!dragging) return;
            dragging = false;
            try {
                if (event && event.pointerId !== undefined) root.releasePointerCapture(event.pointerId);
            } catch (error) { /* ignore */ }
            if (options && options.onCommit) options.onCommit(value);
        }

        root.addEventListener('pointerdown', (event) => {
            if (event.button !== undefined && event.button !== 0) return;
            dragging = true;
            try { root.setPointerCapture(event.pointerId); } catch (error) { /* ignore */ }
            measure();
            const fraction = Math.min(1, Math.max(0, (event.clientX - trackLeft) / Math.max(1, trackWidth)));
            setValue(min + fraction * (max - min), 'pointer');
            if (options && options.onStart) options.onStart(value);
            event.preventDefault();
        });
        root.addEventListener('pointermove', (event) => {
            if (!dragging) return;
            const fraction = Math.min(1, Math.max(0, (event.clientX - trackLeft) / Math.max(1, trackWidth)));
            setValue(min + fraction * (max - min), 'pointer');
        });
        window.addEventListener('resize', refresh, { passive: true });
        root.addEventListener('pointerup', endDrag);
        root.addEventListener('pointercancel', endDrag);
        root.addEventListener('lostpointercapture', () => endDrag(null));
        root.addEventListener('keydown', (event) => {
            let direction = 0;
            if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') direction = -1;
            else if (event.key === 'ArrowRight' || event.key === 'ArrowUp') direction = 1;
            else if (event.key === 'Home') {
                setValue(min, 'key');
                if (options && options.onCommit) options.onCommit(value);
                event.preventDefault();
                return;
            } else if (event.key === 'End') {
                setValue(max, 'key');
                if (options && options.onCommit) options.onCommit(value);
                event.preventDefault();
                return;
            } else {
                return;
            }
            event.preventDefault();
            setValue(value + direction * stepSize, 'key');
            if (options && options.onCommit) options.onCommit(value);
        });

        render(value);
        if (window.ResizeObserver && track) new ResizeObserver(refresh).observe(track);

        return {
            getValue: () => value,
            setValue: (next, silent) => {
                setValue(next, silent ? 'init' : 'api');
                return value;
            },
            refresh: refresh
        };
    }

    /* ---------- Rating dialog ---------- */
    const dialog = document.getElementById('rating-dialog');
    const dialogTabs = Array.prototype.slice.call(document.querySelectorAll('[data-dialog-tab]'));
    const dialogPanels = Array.prototype.slice.call(document.querySelectorAll('[data-dialog-panel]'));
    const ratingModeButtons = Array.prototype.slice.call(document.querySelectorAll('[data-rating-mode]'));
    const ratingModePanels = Array.prototype.slice.call(document.querySelectorAll('[data-rating-panel]'));
    const ratingFootNote = document.getElementById('rating-foot-note');
    const saveRating = document.getElementById('save-rating');
    const quickScoreValue = document.getElementById('quick-score-value');
    const quickScoreLabel = document.getElementById('quick-score-label');
    const quickQualityRoot = document.getElementById('quick-quality-slider');
    const quickDifficultyRoot = document.getElementById('quick-difficulty-slider');
    const quickDifficultyOutput = document.getElementById('quick-difficulty-output');
    const quickDifficultyBlock = document.getElementById('quick-difficulty-block');
    const quickDifficultyToggle = document.getElementById('quick-difficulty-toggle');
    const quickDifficultyLabel = document.getElementById('quick-difficulty-label');
    const quickPresetButtons = Array.prototype.slice.call(document.querySelectorAll('[data-quick-quality-preset]'));
    const quickRealmButtons = Array.prototype.slice.call(document.querySelectorAll('[data-quick-realm]'));
    const qualityRows = Array.prototype.slice.call(document.querySelectorAll('.scale-row[data-quality-dim]'));
    const detailSliderRoots = Array.prototype.slice.call(document.querySelectorAll('[data-diff-slider]'));
    const dialogDifficulty = document.getElementById('dialog-difficulty');
    const dialogShip = document.getElementById('dialog-ship');
    const difficultyNumberEl = document.getElementById('dialog-difficulty-number');
    const difficultyRealmEl = document.getElementById('dialog-difficulty-realm');
    const difficultyContextEl = document.getElementById('dialog-context');
    const qualityAverageEl = document.getElementById('quality-average');
    const qualityPickedEl = document.getElementById('quality-picked');

    let ratingMode = 'quick';
    let quickScore = quickQualityRoot ? Number(quickQualityRoot.dataset.value || quickQualityRoot.getAttribute('aria-valuenow') || 5) : 5;
    let quickQualityTouched = !!(userRatings.quality && userRatings.quality.mode === 'quick');
    let quickDifficultyValue = quickDifficultyRoot ? Number(quickDifficultyRoot.dataset.value || quickDifficultyRoot.getAttribute('aria-valuenow') || 30) : 30;
    let difficultyEnabled = quickDifficultyBlock ? quickDifficultyBlock.dataset.enabled === '1' : false;
    let quickQualitySlider = null;
    let quickDifficultySlider = null;
    const detailSliderRefs = [];

    function quickLabelFor(score) {
        if (score <= 2) return '不太行';
        if (score <= 4) return '一般';
        if (score <= 6) return '还不错';
        if (score <= 8) return '佳作';
        return '神作';
    }
    function quickQualityBand(score) {
        if (score <= 2) return 0;
        if (score <= 4) return 1;
        if (score <= 6) return 2;
        if (score <= 8) return 3;
        return 4;
    }
    function quickDifficultyBand(value) {
        if (value <= 10) return 0;
        if (value <= 20) return 1;
        if (value <= 30) return 2;
        if (value <= 40) return 3;
        if (value <= 55) return 4;
        return 5;
    }

    function renderQuickQuality(score) {
        if (quickScoreValue) quickScoreValue.textContent = Number(score).toFixed(1);
        if (quickScoreLabel) {
            quickScoreLabel.textContent = quickQualityTouched ? quickLabelFor(score) : '拖动滑杆或点选快捷词';
            quickScoreLabel.classList.toggle('is-empty', !quickQualityTouched);
        }
        const band = quickQualityBand(score);
        quickPresetButtons.forEach((button, index) => {
            const active = quickQualityTouched && index === band;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', String(active));
        });
    }

    function renderQuickDifficulty(value) {
        quickDifficultyValue = value;
        if (quickDifficultyOutput) {
            quickDifficultyOutput.textContent = value + ' · ' + getRealm(value);
            const index = quickDifficultyBand(value);
            const color = quickRealmButtons[index] ? quickRealmButtons[index].style.getPropertyValue('--realm-color') : '';
            quickDifficultyOutput.style.color = color;
        }
        const band = quickDifficultyBand(value);
        quickRealmButtons.forEach((button, index) => {
            const active = index === band;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', String(active));
        });
    }

    function selectedQualityCount() {
        return qualityRows.filter((row) => Number(row.dataset.score || 0) > 0).length;
    }
    function detailQualityAverage() {
        const scores = qualityRows.map((row) => Number(row.dataset.score || 0)).filter((value) => value > 0);
        return average(scores);
    }
    function detailDifficultyAverage() {
        return average(detailSliderRefs.map((ref) => ref.slider.getValue()));
    }
    function currentDetailKey() {
        return 'd' + (dialogDifficulty ? dialogDifficulty.value || '0' : '0') + '_s' + (dialogShip ? dialogShip.value || '0' : '0');
    }

    function updateRatingFooter() {
        if (!saveRating) return;
        if (ratingMode === 'quick') {
            saveRating.textContent = userRatings.quality && userRatings.quality.mode === 'quick' ? '更新快速评分' : '提交快速评分';
            saveRating.disabled = !quickQualityTouched;
            if (!quickQualityTouched) {
                ratingFootNote.textContent = '请先拖动滑杆或点选一个整体分';
            } else {
                let note = '将提交 ' + Number(quickScore).toFixed(1) + '/10';
                if (difficultyEnabled) note += ' · ' + quickDifficultyValue + '（' + getRealm(quickDifficultyValue) + '）';
                ratingFootNote.textContent = note;
            }
            return;
        }

        if (!dialog || !saveRating) return;
        const activeTab = document.querySelector('[data-dialog-tab].is-active');
        const tab = activeTab ? activeTab.dataset.dialogTab : 'quality';
        if (tab === 'quality') {
            const count = selectedQualityCount();
            saveRating.textContent = '保存细分品质';
            saveRating.disabled = count < qualityRows.length;
            ratingFootNote.textContent = '已选 ' + count + ' / ' + qualityRows.length + ' 个维度';
        } else {
            saveRating.textContent = '保存细分难度';
            saveRating.disabled = false;
            const contextLabel = dialogDifficulty && dialogShip
                ? (dialogDifficulty.options[dialogDifficulty.selectedIndex].text + ' · ' + dialogShip.options[dialogShip.selectedIndex].text)
                : '游戏总体 · 全机体/角色';
            ratingFootNote.textContent = '将提交 ' + detailDifficultyAverage().toFixed(1) + '/60 · ' + contextLabel;
        }
    }

    function setRatingMode(mode) {
        ratingMode = mode;
        ratingModeButtons.forEach((button) => {
            const active = button.dataset.ratingMode === mode;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-selected', String(active));
        });
        ratingModePanels.forEach((panel) => {
            panel.hidden = panel.dataset.ratingPanel !== mode;
        });
        updateRatingFooter();
        requestAnimationFrame(refreshSliders);
    }

    function setDialogTab(name) {
        dialogTabs.forEach((tab) => {
            const active = tab.dataset.dialogTab === name;
            tab.classList.toggle('is-active', active);
            tab.setAttribute('aria-selected', String(active));
        });
        dialogPanels.forEach((panel) => {
            panel.hidden = panel.dataset.dialogPanel !== name;
        });
        if (name === 'difficulty') syncDetailDifficulty();
        updateRatingFooter();
        requestAnimationFrame(refreshSliders);
    }

    function refreshSliders() {
        if (quickQualitySlider) quickQualitySlider.refresh();
        if (quickDifficultySlider) quickDifficultySlider.refresh();
        detailSliderRefs.forEach((ref) => ref.slider.refresh());
    }

    function setQuickDifficultyOpen(open, include) {
        difficultyEnabled = !!(open && include);
        if (quickDifficultyBlock) quickDifficultyBlock.hidden = !open;
        if (quickDifficultyToggle) {
            quickDifficultyToggle.classList.toggle('is-open', open);
            quickDifficultyToggle.setAttribute('aria-expanded', String(open));
        }
        if (quickDifficultyLabel) quickDifficultyLabel.textContent = open ? '收起难度' : '也评整体难度';
        if (quickDifficultyBlock) quickDifficultyBlock.dataset.enabled = difficultyEnabled ? '1' : '0';
        updateRatingFooter();
    }

    function openRating(kind) {
        if (!dialog) return;
        if (!session.user_id) {
            window.location.href = '/login?redirect=' + encodeURIComponent(window.location.pathname);
            return;
        }
        if (kind === 'quality' || kind === 'difficulty') {
            setDialogTab(kind);
            setRatingMode('detail');
        } else {
            setRatingMode('quick');
        }
        document.body.classList.add('rating-open');
        if (typeof dialog.showModal === 'function') dialog.showModal();
        else dialog.setAttribute('open', '');
        const panel = dialog.querySelector('.rating-panel');
        if (panel) panel.focus({ preventScroll: true });
        requestAnimationFrame(() => {
            refreshSliders();
            if (ratingMode === 'quick' && quickQualityRoot) quickQualityRoot.focus({ preventScroll: true });
        });
    }

    function closeRating() {
        if (!dialog) return;
        if (typeof dialog.close === 'function') dialog.close();
        else dialog.removeAttribute('open');
        document.body.classList.remove('rating-open');
    }

    if (quickQualityRoot) {
        quickQualitySlider = createDemoSlider(quickQualityRoot, {
            value: quickScore,
            onStart: () => {
                quickQualityTouched = true;
                renderQuickQuality(quickScore);
                updateRatingFooter();
            },
            onInput: (value) => {
                quickQualityTouched = true;
                quickScore = value;
                renderQuickQuality(value);
                updateRatingFooter();
            },
            onCommit: (value) => {
                quickQualityTouched = true;
                quickScore = value;
                renderQuickQuality(value);
                updateRatingFooter();
            }
        });
    }
    if (quickDifficultyRoot) {
        quickDifficultySlider = createDemoSlider(quickDifficultyRoot, {
            value: quickDifficultyValue,
            onStart: (value) => {
                difficultyEnabled = true;
                if (quickDifficultyBlock) quickDifficultyBlock.dataset.enabled = '1';
                renderQuickDifficulty(value);
                updateRatingFooter();
            },
            onInput: (value) => {
                difficultyEnabled = true;
                if (quickDifficultyBlock) quickDifficultyBlock.dataset.enabled = '1';
                renderQuickDifficulty(value);
                updateRatingFooter();
            },
            onCommit: (value) => {
                renderQuickDifficulty(value);
                updateRatingFooter();
            }
        });
    }

    quickPresetButtons.forEach((button) => {
        button.addEventListener('click', () => {
            quickQualityTouched = true;
            if (quickQualitySlider) quickQualitySlider.setValue(Number(button.dataset.quickQualityPreset));
            quickScore = quickQualitySlider ? quickQualitySlider.getValue() : Number(button.dataset.quickQualityPreset);
            renderQuickQuality(quickScore);
            updateRatingFooter();
        });
    });
    quickRealmButtons.forEach((button) => {
        button.addEventListener('click', () => {
            difficultyEnabled = true;
            if (quickDifficultyBlock) quickDifficultyBlock.dataset.enabled = '1';
            if (quickDifficultySlider) quickDifficultySlider.setValue(Number(button.dataset.quickRealm));
            quickDifficultyValue = quickDifficultySlider ? quickDifficultySlider.getValue() : Number(button.dataset.quickRealm);
            renderQuickDifficulty(quickDifficultyValue);
            updateRatingFooter();
        });
    });
    if (quickDifficultyToggle) {
        quickDifficultyToggle.addEventListener('click', () => {
            const open = quickDifficultyBlock ? quickDifficultyBlock.hidden : false;
            setQuickDifficultyOpen(open, open);
        });
    }

    ratingModeButtons.forEach((button) => {
        button.addEventListener('click', () => setRatingMode(button.dataset.ratingMode));
    });
    dialogTabs.forEach((tab) => {
        tab.addEventListener('click', () => setDialogTab(tab.dataset.dialogTab));
    });
    document.querySelectorAll('[data-open-rating]').forEach((button) => {
        button.addEventListener('click', () => openRating(button.dataset.openRating));
    });
    document.querySelectorAll('[data-close-rating]').forEach((button) => {
        button.addEventListener('click', closeRating);
    });
    if (dialog) {
        dialog.addEventListener('click', (event) => {
            if (event.target === dialog) closeRating();
        });
        dialog.addEventListener('close', () => document.body.classList.remove('rating-open'));
    }

    qualityRows.forEach((row) => {
        const output = row.querySelector('output');
        const buttons = Array.prototype.slice.call(row.querySelectorAll('.scale button'));
        buttons.forEach((button) => {
            button.addEventListener('click', () => {
                const value = Number(button.dataset.value);
                buttons.forEach((candidate) => {
                    candidate.classList.toggle('is-active', Number(candidate.dataset.value) <= value);
                });
                row.dataset.score = String(value);
                if (output) output.textContent = value + ' / 10';
                if (qualityAverageEl) {
                    const avg = detailQualityAverage();
                    qualityAverageEl.textContent = avg ? avg.toFixed(1) : '—';
                }
                if (qualityPickedEl) qualityPickedEl.textContent = '已选 ' + selectedQualityCount() + ' / ' + qualityRows.length + ' 个维度';
                updateRatingFooter();
            });
        });
    });

    detailSliderRoots.forEach((root) => {
        const row = root.closest('.range-row');
        const output = row ? row.querySelector('output') : null;
        const ref = {
            slider: createDemoSlider(root, {
                value: root.dataset.value,
                onInput: (value) => {
                    if (output) output.textContent = value + ' · ' + getRealm(value);
                },
                onCommit: (value) => {
                    if (output) output.textContent = value + ' · ' + getRealm(value);
                    updateDifficultySummary();
                }
            })
        };
        if (output && ref.slider) output.textContent = ref.slider.getValue() + ' · ' + getRealm(ref.slider.getValue());
        detailSliderRefs.push(ref);
    });

    function updateDifficultySummary() {
        if (!detailSliderRefs.length) return;
        const avg = detailDifficultyAverage();
        if (difficultyNumberEl) difficultyNumberEl.textContent = avg.toFixed(1);
        if (difficultyRealmEl) difficultyRealmEl.textContent = getRealm(avg);
        if (difficultyContextEl && dialogDifficulty && dialogShip) {
            difficultyContextEl.textContent = dialogDifficulty.options[dialogDifficulty.selectedIndex].text + ' · ' + dialogShip.options[dialogShip.selectedIndex].text;
        }
        updateRatingFooter();
    }

    function syncDetailDifficulty() {
        if (!dialogDifficulty || !dialogShip) return;
        const key = currentDetailKey();
        const saved = userRatings.difficulty ? userRatings.difficulty[key] : null;
        detailSliderRefs.forEach((ref) => ref.slider.setValue(30, true));
        if (saved && saved.mode === 'detailed') {
            const values = [saved.dodge, saved.strategy, saved.execution];
            detailSliderRefs.forEach((ref, index) => {
                if (values[index] !== null && values[index] !== undefined) {
                    ref.slider.setValue(values[index], true);
                }
            });
        }
        const outputs = Array.prototype.slice.call(document.querySelectorAll('[data-diff-slider]')).map((root) => root.closest('.range-row').querySelector('output'));
        detailSliderRefs.forEach((ref, index) => {
            if (outputs[index]) {
                const value = ref.slider.getValue();
                outputs[index].textContent = value + ' · ' + getRealm(value);
            }
        });
        updateDifficultySummary();
    }

    if (dialogDifficulty) dialogDifficulty.addEventListener('change', syncDetailDifficulty);
    if (dialogShip) dialogShip.addEventListener('change', syncDetailDifficulty);

    // Initialise a saved quick rating into the dialog.
    if (quickQualitySlider) {
        quickQualitySlider.setValue(quickScore, true);
    }
    if (quickDifficultySlider) {
        quickDifficultySlider.setValue(quickDifficultyValue, true);
    }
    if (quickDifficultyBlock) {
        const open = !quickDifficultyBlock.hidden;
        setQuickDifficultyOpen(open, open && difficultyEnabled);
        if (open && !difficultyEnabled) {
            quickDifficultyBlock.hidden = false;
            if (quickDifficultyToggle) {
                quickDifficultyToggle.classList.add('is-open');
                quickDifficultyToggle.setAttribute('aria-expanded', 'true');
            }
            if (quickDifficultyLabel) quickDifficultyLabel.textContent = '收起难度';
        }
    }
    renderQuickQuality(quickScore);
    renderQuickDifficulty(quickDifficultyValue);
    updateDifficultySummary();
    updateRatingFooter();

    async function finishRating(message) {
        toast(message);
        closeRating();
        window.setTimeout(() => window.location.reload(), 550);
    }

    async function saveQuickRating() {
        if (!quickQualityTouched) {
            toast('请先拖动滑杆或点选一个整体分');
            return;
        }
        const formData = new FormData();
        formData.set('quick_quality', Number(quickScore).toFixed(1));
        if (difficultyEnabled) {
            formData.set('include_difficulty', '1');
            formData.set('quick_difficulty', String(quickDifficultyValue));
        } else {
            formData.set('include_difficulty', '0');
        }
        saveRating.setAttribute('aria-busy', 'true');
        try {
            const response = await fetch('/game/' + gameId + '/rate_quick', { method: 'POST', body: formData });
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || '提交失败');
            finishRating(result.message || '快速评分已保存');
        } catch (error) {
            toast('提交失败：' + error.message);
        } finally {
            saveRating.removeAttribute('aria-busy');
        }
    }

    async function saveDetailedQuality() {
        const scores = {};
        qualityRows.forEach((row) => {
            scores[row.dataset.qualityDim] = Number(row.dataset.score || 0);
        });
        if (Object.values(scores).some((value) => !value)) {
            toast('请先选满 5 个品质维度');
            return;
        }
        const formData = new FormData();
        Object.keys(scores).forEach((category) => {
            formData.set('rating_' + category, String(scores[category]));
        });
        saveRating.setAttribute('aria-busy', 'true');
        try {
            const response = await fetch('/game/' + gameId + '/rate_quality', { method: 'POST', body: formData });
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || '提交失败');
            finishRating(result.message || '细分品质评分已保存');
        } catch (error) {
            toast('提交失败：' + error.message);
        } finally {
            saveRating.removeAttribute('aria-busy');
        }
    }

    async function saveDetailedDifficulty() {
        const formData = new FormData();
        formData.set('difficulty_level_id', dialogDifficulty ? dialogDifficulty.value : '');
        formData.set('ship_type_id', dialogShip ? dialogShip.value : '');
        const fields = ['避弹', '策略', '执行'];
        detailSliderRefs.forEach((ref, index) => {
            formData.set('rating_' + fields[index], String(ref.slider.getValue()));
        });
        saveRating.setAttribute('aria-busy', 'true');
        try {
            const response = await fetch('/game/' + gameId + '/rate_difficulty', { method: 'POST', body: formData });
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || '提交失败');
            finishRating(result.message || '细分难度评分已保存');
        } catch (error) {
            toast('提交失败：' + error.message);
        } finally {
            saveRating.removeAttribute('aria-busy');
        }
    }

    if (saveRating) {
        saveRating.addEventListener('click', () => {
            if (ratingMode === 'quick') {
                saveQuickRating();
                return;
            }
            const activeTab = document.querySelector('[data-dialog-tab].is-active');
            const tab = activeTab ? activeTab.dataset.dialogTab : 'quality';
            if (tab === 'quality') saveDetailedQuality();
            else saveDetailedDifficulty();
        });
    }

    /* ---------- Delete ratings ---------- */
    document.querySelectorAll('[data-delete-quality]').forEach((button) => {
        button.addEventListener('click', async () => {
            if (!confirm('确定要撤销你的品质评分吗？快速与细分评分都会被删除。')) return;
            try {
                const response = await fetch('/game/' + gameId + '/rate_quality', { method: 'DELETE' });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || '撤销失败');
                window.location.reload();
            } catch (error) {
                toast('撤销失败：' + error.message);
            }
        });
    });

    document.querySelectorAll('[data-delete-difficulty]').forEach((button) => {
        button.addEventListener('click', async () => {
            if (!confirm('确定要撤销该情境下的难度评分吗？')) return;
            const params = new URLSearchParams();
            if (button.dataset.levelId) params.set('difficulty_level_id', button.dataset.levelId);
            if (button.dataset.shipId) params.set('ship_type_id', button.dataset.shipId);
            try {
                const response = await fetch('/game/' + gameId + '/rate_difficulty?' + params.toString(), { method: 'DELETE' });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || '撤销失败');
                window.location.reload();
            } catch (error) {
                toast('撤销失败：' + error.message);
            }
        });
    });

    /* ---------- Admin delete game ---------- */
    const deleteGameButton = document.getElementById('delete-game-button');
    if (deleteGameButton) {
        deleteGameButton.addEventListener('click', async () => {
            const title = deleteGameButton.dataset.gameTitle;
            const confirmation = prompt('这是一个危险操作！\n要删除游戏 "' + title + '"，请输入它的名字进行确认:');
            if (confirmation !== title) {
                toast('名称输入错误，删除操作已取消。');
                return;
            }
            if (!confirm('最后确认：真的要永久删除 "' + title + '" 吗？此操作无法撤销！')) {
                toast('删除操作已取消。');
                return;
            }
            try {
                const response = await fetch('/admin/game/' + deleteGameButton.dataset.gameId, { method: 'DELETE' });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || '删除失败');
                alert(result.message);
                window.location.href = '/games';
            } catch (error) {
                toast('删除失败：' + error.message);
            }
        });
    }

    /* ---------- Theme / icons ---------- */
    document.addEventListener('themeChanged', () => {
        if (window.lucide) window.lucide.createIcons();
    });
    if (window.lucide) window.lucide.createIcons();
});
