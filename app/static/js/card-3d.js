// 卡片3D鼠标跟随效果
document.addEventListener('DOMContentLoaded', function() {
    // 检查用户是否偏好减少动画
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    
    if (prefersReducedMotion) {
        return; // 如果用户偏好减少动画，则不应用3D效果
    }
    
    // 获取所有卡片容器
    const cardContainers = document.querySelectorAll('.game-link-container, .articles-list article.card, .bounties-list article.card');
    
    cardContainers.forEach(container => {
        const card = container.querySelector('.game-card') || container;
        
        // 添加鼠标跟随效果类
        if (card) {
            card.classList.add('mouse-tilt');
        }
        
        container.addEventListener('mousemove', function(e) {
            const rect = container.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            // 计算鼠标相对于卡片中心的位置（-1 到 1）
            const centerX = rect.width / 2;
            const centerY = rect.height / 2;
            const rotateX = (y - centerY) / centerY * -5; // 最大5度
            const rotateY = (x - centerX) / centerX * 5;   // 最大5度
            
            // 应用3D变换
            if (card) {
                const currentTransform = card.style.transform || '';
                // 保留原有的translateY，添加旋转
                const baseTransform = currentTransform.match(/translateY\([^)]+\)/) || ['translateY(-8px)'];
                card.style.transform = `${baseTransform[0]} translateZ(20px) rotateX(${rotateX}deg) rotateY(${rotateY}deg)`;
            }
        });
        
        container.addEventListener('mouseleave', function() {
            if (card) {
                // 恢复默认状态
                card.style.transform = '';
            }
        });
    });
});

