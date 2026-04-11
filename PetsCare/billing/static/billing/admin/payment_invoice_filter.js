/* global django */
(function () {
  function getUnpaidInvoicesUrl() {
    const path = window.location.pathname || "";
    const match = path.match(/^(.+\/payment\/)/);
    const prefix = match ? match[1] : "/admin/billing/payment/";
    return prefix + "unpaid-invoices/";
  }

  function reloadInvoices() {
    const provider = document.getElementById("id_provider");
    const invoice = document.getElementById("id_invoice");
    if (!provider || !invoice) return;

    const pid = provider.value;
    if (!pid) {
      while (invoice.options.length) {
        invoice.remove(0);
      }
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = "---------";
      invoice.appendChild(empty);
      return;
    }

    const url = getUnpaidInvoicesUrl() + "?provider_id=" + encodeURIComponent(pid);
    const xhr = new XMLHttpRequest();
    xhr.open("GET", url, true);
    xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");
    xhr.onload = function () {
      if (xhr.status !== 200) return;
      let data;
      try {
        data = JSON.parse(xhr.responseText);
      } catch (e) {
        return;
      }
      const current = invoice.value;
      while (invoice.options.length) {
        invoice.remove(0);
      }
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "---------";
      invoice.appendChild(placeholder);
      const rows = data.invoices || [];
      for (let i = 0; i < rows.length; i++) {
        const opt = document.createElement("option");
        opt.value = String(rows[i].id);
        opt.textContent = rows[i].label || String(rows[i].id);
        invoice.appendChild(opt);
      }
      if (current) {
        invoice.value = current;
      }
    };
    xhr.send();
  }

  document.addEventListener("DOMContentLoaded", function () {
    const provider = document.getElementById("id_provider");
    if (!provider) return;
    provider.addEventListener("change", reloadInvoices);
    if (provider.value) {
      reloadInvoices();
    }
  });
})();
