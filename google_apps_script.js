// ─────────────────────────────────────────
// EasyEducation AI Voice Agent — Google Apps Script
// Handles: Outbound trigger + Inbound logging + Lead capture
// Tabs: Outbound | Inbound | Leads
// ─────────────────────────────────────────

// ─────────────────────────────────────────
// CONFIG
// ─────────────────────────────────────────
function getConfig() {
  const props = PropertiesService.getScriptProperties().getProperties();
  return {
    spreadsheetId: props.SPREADSHEET_ID,
    webhookUrl:    props.EC2_WEBHOOK_URL,
    secret:        props.WEBHOOK_SECRET,
  };
}

// ─────────────────────────────────────────
// WEB APP — receives POST from EC2 agent
// ─────────────────────────────────────────
function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const action = data.action || 'log_inbound';
    if (action === 'log_lead') return logLead(data);
    return logInbound(data);
  } catch (err) {
    return ContentService.createTextOutput(
      JSON.stringify({ status: 'error', message: err.toString() })
    ).setMimeType(ContentService.MimeType.JSON);
  }
}

// ─────────────────────────────────────────
// LOG INBOUND CALL
// ─────────────────────────────────────────
function logInbound(data) {
  const cfg = getConfig();
  const ss = SpreadsheetApp.openById(cfg.spreadsheetId);
  const sheet = ss.getSheetByName('Inbound');

  if (!sheet) return ContentService.createTextOutput(
    JSON.stringify({ status: 'error', message: 'Inbound tab not found' })
  ).setMimeType(ContentService.MimeType.JSON);

  if (sheet.getLastRow() === 0) {
    sheet.appendRow(['Caller Number', 'Language', 'Call Date', 'Call Time', 'Duration (mins)']);
    sheet.getRange(1, 1, 1, 5).setFontWeight('bold').setBackground('#4285F4').setFontColor('#FFFFFF');
  }

  sheet.appendRow([
    data.caller_number    || '',
    data.language         || '',
    data.call_date        || '',
    data.call_time        || '',
    data.duration_minutes || '',
  ]);

  return ContentService.createTextOutput(JSON.stringify({ status: 'ok' }))
    .setMimeType(ContentService.MimeType.JSON);
}

// ─────────────────────────────────────────
// LOG LEAD
// ─────────────────────────────────────────
function logLead(data) {
  const cfg = getConfig();
  const ss = SpreadsheetApp.openById(cfg.spreadsheetId);
  let sheet = ss.getSheetByName('Leads');

  if (!sheet) {
    sheet = ss.insertSheet('Leads');
    sheet.appendRow(['Phone', 'Name', 'Grade', 'Language', 'Interest', 'Call Date', 'Call Time']);
    sheet.getRange(1, 1, 1, 7).setFontWeight('bold').setBackground('#34A853').setFontColor('#FFFFFF');
  }

  sheet.appendRow([
    data.phone     || '',
    data.name      || 'Unknown',
    data.grade     || 'Unknown',
    data.language  || '',
    data.interest  || 'Medium',
    data.call_date || '',
    data.call_time || '',
  ]);

  return ContentService.createTextOutput(JSON.stringify({ status: 'ok' }))
    .setMimeType(ContentService.MimeType.JSON);
}

// ─────────────────────────────────────────
// OUTBOUND TRIGGER — runs every 1 min
// Columns: A=Phone, B=Topic, C=Language, D=Status, E=Called At
// ─────────────────────────────────────────
function checkOutbound() {
  const cfg = getConfig();
  if (!cfg.webhookUrl || !cfg.spreadsheetId) return;

  const ss = SpreadsheetApp.openById(cfg.spreadsheetId);
  const sheet = ss.getSheetByName('Outbound');
  if (!sheet) return;

  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return;

  const data = sheet.getRange(2, 1, lastRow - 1, 5).getValues();

  data.forEach((row, i) => {
    const phone    = row[0]?.toString().trim();
    const topic    = row[1]?.toString().trim() || "";
    const language = row[2]?.toString().trim() || "English";
    const status   = row[3]?.toString().trim();
    if (!phone || status) return;

    const rowNum = i + 2;
    sheet.getRange(rowNum, 4).setValue('Calling...');

    try {
      const response = UrlFetchApp.fetch(cfg.webhookUrl, {
        method: 'post',
        contentType: 'application/json',
        payload: JSON.stringify({
          phone_number: phone,
          topic:        topic,
          language:     language,
          secret:       cfg.secret
        }),
        muteHttpExceptions: true,
      });
      const code = response.getResponseCode();
      sheet.getRange(rowNum, 4).setValue(code === 200 ? 'Called ✓' : `Error ${code}`);
      sheet.getRange(rowNum, 5).setValue(new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }));
    } catch (err) {
      sheet.getRange(rowNum, 4).setValue('Failed');
    }
  });
}

// ─────────────────────────────────────────
// ONE-TIME SETUP
// ─────────────────────────────────────────
function setupSheets() {
  const cfg = getConfig();
  const ss = SpreadsheetApp.openById(cfg.spreadsheetId);

  // Outbound tab — Phone | Topic | Language | Status | Called At
  let outbound = ss.getSheetByName('Outbound');
  if (!outbound) outbound = ss.insertSheet('Outbound');
  if (outbound.getLastRow() === 0) {
    outbound.appendRow(['Phone Number', 'Topic', 'Language', 'Status', 'Called At']);
    outbound.getRange(1, 1, 1, 5).setFontWeight('bold').setBackground('#34A853').setFontColor('#FFFFFF');
  }

  // Inbound tab
  let inbound = ss.getSheetByName('Inbound');
  if (!inbound) inbound = ss.insertSheet('Inbound');
  if (inbound.getLastRow() === 0) {
    inbound.appendRow(['Caller Number', 'Language', 'Call Date', 'Call Time', 'Duration (mins)']);
    inbound.getRange(1, 1, 1, 5).setFontWeight('bold').setBackground('#4285F4').setFontColor('#FFFFFF');
  }

  // Leads tab
  let leads = ss.getSheetByName('Leads');
  if (!leads) leads = ss.insertSheet('Leads');
  if (leads.getLastRow() === 0) {
    leads.appendRow(['Phone', 'Name', 'Grade', 'Language', 'Interest', 'Call Date', 'Call Time']);
    leads.getRange(1, 1, 1, 7).setFontWeight('bold').setBackground('#34A853').setFontColor('#FFFFFF');
  }
}
