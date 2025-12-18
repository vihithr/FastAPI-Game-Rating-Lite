// /app/static/js/game-forms.js

document.addEventListener('DOMContentLoaded', () => {
    // 这部分代码只在含有 id="game-form" 的页面 (添加/编辑页) 上执行
    const gameForm = document.getElementById('game-form');
    if (!gameForm) {
        return;
    }

    // --- 1. 数据初始化 (仅在编辑页有效) ---
    const initialData = JSON.parse(document.getElementById('game-structure-data')?.textContent || '{}');

    // --- 2. 通用动态列表管理器 (别名, 难度) ---
    const createSimpleListManager = (listId, buttonId, initialItems, placeholder) => {
        const listContainer = document.getElementById(listId);
        if (!listContainer) return;
        new Sortable(listContainer, { animation: 150, handle: '.drag-handle' });

        const addItem = (item = { name: '' }) => {
            const div = document.createElement('div');
            div.className = 'dynamic-list-item';
            div.innerHTML = `
                <span class="drag-handle"><i data-lucide="grip-vertical"></i></span>
                <input type="text" class="item-name" placeholder="${placeholder}" value="${item.name || ''}" required>
                <button type="button" class="remove-btn"><i data-lucide="x"></i></button>
            `;
            listContainer.appendChild(div);
            div.querySelector('.remove-btn').addEventListener('click', () => div.remove());
        };
        document.getElementById(buttonId).addEventListener('click', () => addItem());
        if (initialItems && Array.isArray(initialItems)) initialItems.forEach(addItem);
    };

    // --- 3. 机体/角色列表的特殊管理器 ---
    const createShipManager = (listId, buttonId, initialShips) => {
        const shipsListContainer = document.getElementById(listId);
        if (!shipsListContainer) return;
        const addShip = (ship = { name: '', children: [] }) => {
            const shipBlock = document.createElement('div');
            shipBlock.className = 'ship-block';
            const enhancementListId = `enhancements-${Math.random().toString(36).substr(2, 9)}`;
            shipBlock.innerHTML = `
                <fieldset>
                    <legend class="dynamic-list-item">
                        <input type="text" class="ship-name" placeholder="机体/角色名" value="${ship.name || ''}" required>
                        <button type="button" class="remove-btn remove-ship-btn"><i data-lucide="trash-2"></i></button>
                    </legend>
                    <div class="enhancements-list" id="${enhancementListId}" style="margin-left: 2rem;"></div>
                    <button type="button" class="secondary outline add-enhancement-btn" style="margin-left: 2rem; margin-top: 0.5rem;"><i data-lucide="plus"></i> 添加形态/配置</button>
                </fieldset>`;
            shipsListContainer.appendChild(shipBlock);
            const enhancementsList = shipBlock.querySelector('.enhancements-list');
            const addEnhancement = (enhancement = { name: '' }) => {
                const div = document.createElement('div');
                div.className = 'dynamic-list-item';
                div.innerHTML = `<input type="text" class="enhancement-name" placeholder="形态/配置名" value="${enhancement.name || ''}" required><button type="button" class="remove-btn"><i data-lucide="x"></i></button>`;
                enhancementsList.appendChild(div);
                div.querySelector('.remove-btn').addEventListener('click', () => div.remove());
            };
            shipBlock.querySelector('.add-enhancement-btn').addEventListener('click', () => addEnhancement());
            shipBlock.querySelector('.remove-ship-btn').addEventListener('click', () => shipBlock.remove());
            if (ship.children && Array.isArray(ship.children)) ship.children.forEach(addEnhancement);
        };
        document.getElementById(buttonId).addEventListener('click', () => addShip());
        if (initialShips && Array.isArray(initialShips)) initialShips.forEach(addShip);
    };

    // --- 4. 激活所有管理器 ---
    createSimpleListManager('aliases-list', 'add-alias-btn', initialData.aliases, '输入别名或译名');
    createSimpleListManager('difficulties-list', 'add-difficulty-btn', initialData.difficulties, '输入难度名称');
    createShipManager('ships-list', 'add-ship-btn', initialData.ships);

    // --- 5. 表单提交时的序列化逻辑 ---
    gameForm.addEventListener('submit', (e) => {
        const serializeSimpleList = (listId) => Array.from(document.querySelectorAll(`#${listId} .dynamic-list-item`)).map(item => ({ name: item.querySelector('.item-name').value }));
        document.getElementById('aliases-json-input').value = JSON.stringify(serializeSimpleList('aliases-list'));
        document.getElementById('difficulties-json-input').value = JSON.stringify(serializeSimpleList('difficulties-list'));
        const ships = Array.from(document.querySelectorAll('#ships-list .ship-block')).map(shipBlock => {
            const enhancementList = shipBlock.querySelector('.enhancements-list');
            return {
                name: shipBlock.querySelector('.ship-name').value,
                children: Array.from(enhancementList.querySelectorAll('.dynamic-list-item')).map(item => ({ name: item.querySelector('.enhancement-name').value }))
            };
        });
        document.getElementById('ships-json-input').value = JSON.stringify(ships);
    });

    // 确保图标被渲染
    if (window.lucide) {
        lucide.createIcons();
    }
});