/* Fala Comunidade — utilidades compartilhadas */
(function (raiz) {
  'use strict';

  const DIA_MS = 24 * 60 * 60 * 1000;

  const FalaUtil = {
    /** Remove acentos e baixa a caixa, para comparação de texto em PT-BR. */
    normalizar(texto) {
      return String(texto || '')
        .toLowerCase()
        .normalize('NFD')
        .replace(/[̀-ͯ]/g, '');
    },

    id() {
      return 'id-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
    },

    agoraISO() {
      return new Date().toISOString();
    },

    diasAtras(n) {
      return new Date(Date.now() - n * DIA_MS).toISOString();
    },

    diasAFrente(n) {
      return new Date(Date.now() + n * DIA_MS).toISOString();
    },

    /** Diferença em dias inteiros entre hoje e a data (positivo = futuro). */
    diasAte(iso) {
      const alvo = new Date(iso);
      const hoje = new Date();
      alvo.setHours(0, 0, 0, 0);
      hoje.setHours(0, 0, 0, 0);
      return Math.round((alvo - hoje) / DIA_MS);
    },

    dentroDeDias(iso, dias) {
      const delta = (Date.now() - new Date(iso).getTime()) / DIA_MS;
      return delta >= 0 && delta <= dias;
    },

    fmtData(iso) {
      if (!iso) return '—';
      return new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
    },

    fmtDataHora(iso) {
      if (!iso) return '—';
      return new Date(iso).toLocaleDateString('pt-BR', {
        day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
      });
    },

    fmtDataExtensa(iso) {
      if (!iso) return '—';
      return new Date(iso).toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' });
    },

    /** Rótulo relativo amigável para prazos: "vence hoje", "3 dias atrasado"… */
    rotuloPrazo(iso) {
      const d = FalaUtil.diasAte(iso);
      if (d === 0) return 'vence hoje';
      if (d === 1) return 'vence amanhã';
      if (d > 1) return `vence em ${d} dias`;
      if (d === -1) return '1 dia em atraso';
      return `${-d} dias em atraso`;
    },

    escapeHTML(texto) {
      return String(texto == null ? '' : texto)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    },

    plural(n, singular, plural) {
      return n === 1 ? `${n} ${singular}` : `${n} ${plural}`;
    },

    /** Cópia para a área de transferência com fallback. */
    async copiar(texto) {
      try {
        await navigator.clipboard.writeText(texto);
        return true;
      } catch (e) {
        const ta = document.createElement('textarea');
        ta.value = texto;
        document.body.appendChild(ta);
        ta.select();
        const ok = document.execCommand('copy');
        ta.remove();
        return ok;
      }
    },

    async compartilhar(titulo, texto) {
      if (navigator.share) {
        try {
          await navigator.share({ title: titulo, text: texto });
          return true;
        } catch (e) {
          if (e && e.name === 'AbortError') return false;
        }
      }
      return FalaUtil.copiar(texto);
    },

    baixarArquivo(nome, conteudo, tipo) {
      const blob = new Blob([conteudo], { type: tipo || 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = nome;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
    },
  };

  raiz.FalaUtil = FalaUtil;
})(typeof self !== 'undefined' ? self : globalThis);
