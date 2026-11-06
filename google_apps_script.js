// ─────────────────────────────────────────
// Aivoro Hospital AI Assistant — Google Apps Script
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
    if (action === 'save_srm_feedback') return saveSrmFeedback(data);
    if (action === 'book_appointment') return bookAppointment(data);
    if (action === 'log_lead') return logLead(data);
    return logInbound(data);
  } catch (err) {
    return ContentService.createTextOutput(
      JSON.stringify({ status: 'error', message: err.toString() })
    ).setMimeType(ContentService.MimeType.JSON);
  }
}

// Saved feedback is available to the S-R-M Travels team in the spreadsheet.
function saveSrmFeedback(data) {
  const cfg = getConfig();
  if (!cfg.secret || data.secret !== cfg.secret) {
    return ContentService.createTextOutput(JSON.stringify({ status: 'error', message: 'Unauthorized' }))
      .setMimeType(ContentService.MimeType.JSON);
  }
  const safe = value => {
    const text = String(value || '');
    return /^[\s]*[=+\-@]/.test(text) ? "'" + text : text;
  };
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const ss = SpreadsheetApp.openById(cfg.spreadsheetId);
    let sheet = ss.getSheetByName('SRM Feedback');
    if (!sheet) sheet = ss.insertSheet('SRM Feedback');
    if (!sheet.getLastRow()) sheet.appendRow(['Recorded At', 'Phone', 'Rating', 'Feedback']);
    sheet.appendRow([new Date(), safe(data.phone), safe(data.rating), safe(data.feedback)]);
    SpreadsheetApp.flush();
    return ContentService.createTextOutput(JSON.stringify({ status: 'ok' }))
      .setMimeType(ContentService.MimeType.JSON);
  } finally {
    lock.releaseLock();
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
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) return;
  try { checkOutboundLocked(); } finally { lock.releaseLock(); }
}

function checkOutboundLocked() {
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
    SpreadsheetApp.flush();

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

  appointmentSheet(ss);

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


// Requests remain Pending until reception verifies availability and sets Confirmed.
function appointmentSheet(ss) {
  let sheet = ss.getSheetByName('Appointments');
  if (!sheet) sheet = ss.insertSheet('Appointments');
  if (!sheet.getLastRow()) {
    sheet.appendRow(['Appointment ID', 'Patient Name', 'Phone', 'Department',
      'Appointment At', 'Language', 'Reminder Consent', 'Status', 'Reminder At', 'Reminder Status']);
    sheet.setFrozenRows(1);
    sheet.getRange('C:C').setNumberFormat('@');
  }
  return sheet;
}

function bookingResponse(data) {
  return ContentService.createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

function bookAppointment(data) {
  const cfg = getConfig();
  if (!cfg.secret || data.secret !== cfg.secret) {
    return bookingResponse({status: 'error', message: 'Unauthorized'});
  }
  const when = new Date(data.appointment_at);
  if (!data.patient_name || !data.phone || !data.department ||
      isNaN(when.getTime()) || when <= new Date()) {
    return bookingResponse({status: 'error', message: 'Valid future appointment details required'});
  }
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sheet = appointmentSheet(SpreadsheetApp.openById(cfg.spreadsheetId));
    const id = Utilities.getUuid();
    // Prefix user text to prevent spreadsheet formula execution.
    const text = value => "'" + String(value || '');
    sheet.appendRow([id, text(data.patient_name), text(data.phone), text(data.department),
      when, text(data.language || 'English'), data.reminder_consent === true,
      'Pending', new Date(when.getTime() - 60 * 60 * 1000), '']);
    return bookingResponse({status: 'ok', appointment_id: id});
  } finally {
    lock.releaseLock();
  }
}

// Run every minute. Only confirmed appointments with explicit consent are called.
function checkReminders() {
  const cfg = getConfig();
  if (!cfg.webhookUrl || !cfg.secret || !cfg.spreadsheetId) return;
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) return;
  try {
    const sheet = appointmentSheet(SpreadsheetApp.openById(cfg.spreadsheetId));
    if (sheet.getLastRow() < 2) return;
    const rows = sheet.getRange(2, 1, sheet.getLastRow() - 1, 10).getValues();
    const now = new Date();
    rows.forEach((row, index) => {
      const when = new Date(row[4]);
      const remindAt = new Date(row[8]);
      if (row[7] !== 'Confirmed' || row[6] !== true || row[9] ||
          isNaN(when.getTime()) || isNaN(remindAt.getTime()) || remindAt > now || when <= now) return;
      const rowNum = index + 2;
      sheet.getRange(rowNum, 10).setValue('Dispatching');
      SpreadsheetApp.flush();
      try {
        const response = UrlFetchApp.fetch(cfg.webhookUrl, {
          method: 'post', contentType: 'application/json', muteHttpExceptions: true,
          payload: JSON.stringify({phone_number: String(row[2]), language: String(row[5]) || 'English',
            call_mode: 'appointment-reminder', recipient_name: String(row[1]),
            appointment_at: when.toISOString(), secret: cfg.secret})
        });
        sheet.getRange(rowNum, 10).setValue(response.getResponseCode() === 200 ? 'Dispatched' : 'Error: review before retry');
      } catch (err) {
        sheet.getRange(rowNum, 10).setValue('Unknown: review before retry');
      }
    });
  } finally {
    lock.releaseLock();
  }
}
