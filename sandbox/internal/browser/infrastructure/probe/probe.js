() => {
    // 1. 清理上一轮扫描注入的历史标记
    document.querySelectorAll('[data-agent-id]').forEach(el => {
        el.removeAttribute('data-agent-id');
    });

    const interactiveElements = [];
    let currentId = 1;

    const IGNORE_TAGS = new Set([
        'script', 'style', 'svg', 'path', 'noscript', 'iframe',
        'canvas', 'template', 'meta', 'link', 'head', 'title', 'source'
    ]);

    const SEMANTIC_CONTAINERS = new Set([
        'header', 'nav', 'main', 'section', 'article', 'aside', 'footer',
        'form', 'fieldset', 'dialog', 'table', 'tbody', 'thead', 'tr',
        'ul', 'ol', 'li'
    ]);

    // 辅助函数：判断元素是否在页面可见
    function isElementVisible(el) {
        if (el.nodeType !== Node.ELEMENT_NODE) return true;
        const tagName = el.tagName.toLowerCase();
        if (IGNORE_TAGS.has(tagName)) return false;

        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) {
            if (el.children.length === 0) return false;
        }

        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
            return false;
        }
        return true;
    }

    // 辅助函数：提取有效紧凑文本
    function extractText(el) {
        let text = el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('alt') || '';
        text = text.trim().replace(/\s+/g, ' ');
        return text.slice(0, 80);
    }

    // 辅助函数：提取最近有意义的父级容器标题
    function getContextText(el) {
        const container = el.closest('li, article, section, [class*="card"], [class*="item"], [class*="box"], [class*="row"], tr, form');
        if (container && container !== el) {
            const titleEl = container.querySelector('h1, h2, h3, h4, h5, [class*="title"], [class*="name"], [class*="header"], strong');
            if (titleEl && titleEl !== el && !el.contains(titleEl)) {
                return (titleEl.innerText || titleEl.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 60);
            }
        }
        return '';
    }

    // 辅助函数：判断节点是否具备可交互特征
    function isInteractiveElement(el) {
        const tagName = el.tagName.toLowerCase();
        const role = (el.getAttribute('role') || '').toLowerCase();
        const style = window.getComputedStyle(el);

        const isStandard = ['button', 'a', 'input', 'select', 'textarea', 'summary'].includes(tagName);
        const isRole = ['button', 'link', 'tab', 'menuitem', 'checkbox', 'radio', 'switch', 'option'].includes(role);
        const hasPointer = style.cursor === 'pointer';
        const hasClick = typeof el.onclick === 'function' || el.hasAttribute('onclick') || el.hasAttribute('@click') || el.hasAttribute('v-on:click');
        const hasTabIndex = el.hasAttribute('tabindex') && el.getAttribute('tabindex') !== '-1';

        return isStandard || isRole || hasPointer || hasClick || hasTabIndex;
    }

    // 递归生成树状层级节点
    function traverse(node, depth = 0) {
        if (depth > 12) return [];
        const indent = '  '.repeat(depth);
        const lines = [];

        if (node.nodeType === Node.TEXT_NODE) {
            const text = node.textContent.trim().replace(/\s+/g, ' ');
            if (text.length > 0) {
                const parentTag = node.parentElement ? node.parentElement.tagName.toLowerCase() : '';
                if (!['h1','h2','h3','h4','h5','h6','button','a','script','style'].includes(parentTag)) {
                    lines.push(`${indent}- Text "${text.slice(0, 100)}"`);
                }
            }
            return lines;
        }

        if (node.nodeType !== Node.ELEMENT_NODE) return [];
        if (!isElementVisible(node)) return [];

        const el = node;
        const tagName = el.tagName.toLowerCase();
        const style = window.getComputedStyle(el);
        const role = (el.getAttribute('role') || '').toLowerCase();
        const isStandard = ['button', 'a', 'input', 'select', 'textarea', 'summary'].includes(tagName);
        const hasChildControls = el.querySelector('button, a, input, select, textarea');

        // 1. 判断是否为独立的终端可交互元素（若 div 包含子链接/子按钮，则不作为单个元素打标，而是继续遍历其子元素）
        if (isInteractiveElement(el) && (isStandard || !hasChildControls)) {
            const elId = currentId++;
            el.setAttribute('data-agent-id', elId.toString());

            const text = extractText(el);
            const contextText = getContextText(el);
            const placeholder = el.getAttribute('placeholder') || '';
            const href = el.getAttribute('href') || '';
            const value = (el.value !== undefined && el.value !== null) ? String(el.value).slice(0, 50) : '';
            const isDisabled = el.disabled === true || el.getAttribute('aria-disabled') === 'true';

            let extra = '';
            if (placeholder) extra += ` placeholder="${placeholder}"`;
            if (value) extra += ` value="${value}"`;
            if (href) extra += ` -> ${href}`;
            if (isDisabled) extra += ' [已禁用]';

            const tagLabel = tagName.toUpperCase();
            lines.push(`${indent}- [${elId}] (${tagLabel}) "${text}"${extra}`);

            interactiveElements.push({
                id: elId,
                tag_name: tagLabel,
                text: text,
                role: role || (style.cursor === 'pointer' ? 'button' : ''),
                context_text: contextText,
                placeholder: placeholder,
                value: value,
                href: href,
                is_disabled: isDisabled
            });

            // 终端按钮/链接无需再输出其内部纯展示子节点
            if (isStandard) {
                return lines;
            }
        }

        // 2. 标题元素 (H1 - H6)
        if (/^h[1-6]$/.test(tagName)) {
            const headingText = extractText(el);
            if (headingText) {
                lines.push(`${indent}- (${tagName.toUpperCase()}) "${headingText}"`);
            }
            return lines;
        }

        // 3. 段落元素 (P)
        if (tagName === 'p') {
            const pText = extractText(el);
            const hasSubInteractive = el.querySelector('button, a, input, select, textarea');
            if (!hasSubInteractive && pText) {
                lines.push(`${indent}- (P) "${pText.slice(0, 120)}"`);
                return lines;
            }
        }

        // 4. 递归遍历子元素
        const childLines = [];
        for (const child of el.childNodes) {
            const res = traverse(child, depth + 1);
            if (res && res.length > 0) {
                childLines.push(...res);
            }
        }

        // 5. 语义容器包装（如 Header, Nav, Main, Section, Article, Form, Table, Card）
        const isContainer = SEMANTIC_CONTAINERS.has(tagName);
        const className = (typeof el.className === 'string' ? el.className : '').toLowerCase();
        const isCardLike = /card|item|panel|box|modal|dialog|banner|container/.test(className) && childLines.length > 0;

        if ((isContainer || isCardLike) && childLines.length > 0 && !el.hasAttribute('data-agent-id')) {
            let containerLabel = tagName.toUpperCase();
            if (isCardLike && !isContainer) {
                containerLabel = 'Card';
            }
            let titleAttr = el.getAttribute('aria-label') || el.getAttribute('title') || '';
            let labelExtra = titleAttr ? ` "${titleAttr.slice(0, 40)}"` : '';

            lines.push(`${indent}- [${containerLabel}]${labelExtra}`);
            lines.push(...childLines);
        } else {
            lines.push(...childLines);
        }

        return lines;
    }

    const treeLines = traverse(document.body || document.documentElement, 0);

    return {
        elements: interactiveElements,
        dom_tree: treeLines.join('\n')
    };
}
