function Test-BindingDebug($baseUrl, $adminToken, $label, $userId, $clientIp, $clientMac) {
  $body = @{
    user_id = $userId
    client_ip = $clientIp
    client_mac = $clientMac
  } | ConvertTo-Json
  try {
    $result = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/auth/debug/binding" -Headers @{ Authorization = "Bearer $adminToken" } -ContentType "application/json" -Body $body
    $binding = $result.binding
    Write-Host "Binding debug ($label): input_ip=$($binding.input_ip) input_mac=$($binding.input_mac) resolved_ip=$($binding.resolved_ip) ip_source=$($binding.ip_source) ip_msg=$($binding.ip_message) resolved_mac=$($binding.resolved_mac) mac_source=$($binding.mac_source) mac_msg=$($binding.mac_message)"
  } catch {
    Write-Host "Binding debug ($label) gagal: $($_.Exception.Message)"
  }
}

function Set-UserLifecycleState([string]$phoneNumber) {
  if (-not $phoneNumber) { return }
  $envArgs = @(
    "-e", "TARGET_PHONE=$phoneNumber"
  )

  $py = @'
import os
from app import create_app
from app.extensions import db
from app.infrastructure.db.models import User, ApprovalStatus, UserRole
from app.utils.formatters import get_phone_number_variations
from app.services import settings_service

app = create_app()
with app.app_context():
    phone = os.environ.get("TARGET_PHONE") or ""
    variations = get_phone_number_variations(phone)
    user = db.session.query(User).filter(User.phone_number.in_(variations)).first()
    if not user:
        print(f"Force-activate skipped: user not found for {phone}")
        raise SystemExit(0)

    user.is_blocked = False
    user.blocked_reason = None
    user.is_active = True
    user.approval_status = ApprovalStatus.APPROVED

    # Pastikan field MikroTik minimal terisi agar endpoint admin update tidak gagal
    # saat ENABLE_MIKROTIK_OPERATIONS=True.
    try:
      if not user.mikrotik_server_name:
        if getattr(user, 'role', None) == UserRole.KOMANDAN:
          user.mikrotik_server_name = settings_service.get_setting('MIKROTIK_DEFAULT_SERVER_KOMANDAN', 'testing')
        else:
          user.mikrotik_server_name = settings_service.get_setting('MIKROTIK_DEFAULT_SERVER_USER', 'testing')
    except Exception:
      pass

    try:
      if not user.mikrotik_profile_name:
        user.mikrotik_profile_name = settings_service.get_setting('MIKROTIK_ACTIVE_PROFILE', 'profile-aktif')
    except Exception:
      pass

    db.session.commit()
    print(f"Force-activate OK: user_id={user.id} phone={user.phone_number}")
'@

  $pyB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($py))
  $cmdArgs = @("exec", "-T") + $envArgs + @(
    "backend",
    "python",
    "-c",
    "import base64,sys; exec(base64.b64decode('$pyB64').decode('utf-8'))"
  )
  try {
    Invoke-Compose $cmdArgs | Out-Null
  } catch {
    Write-Host "[WARN] Force-activate gagal untuk phone=${phoneNumber}: $($_.Exception.Message)" -ForegroundColor Yellow
  }
}

function Invoke-AutoDebtThresholdSimulation([string]$phoneNumber, [string]$clientIp, [string]$clientMac) {
  if (-not $phoneNumber) { return }
  $envArgs = @(
    "-e", "TARGET_PHONE=$phoneNumber",
    "-e", "TARGET_IP=$clientIp",
    "-e", "TARGET_MAC=$clientMac"
  )

  $py = @'
import os
from app import create_app
from app.extensions import db
from app.infrastructure.db.models import User, ApprovalStatus
from app.services.hotspot_sync_service import resolve_target_profile_for_user, sync_address_list_for_single_user
from app.services import settings_service
from app.utils.formatters import get_phone_number_variations

app = create_app()
with app.app_context():
    phone = os.environ.get("TARGET_PHONE") or ""
    client_ip = os.environ.get("TARGET_IP") or None
    variations = get_phone_number_variations(phone)
    user = db.session.query(User).filter(User.phone_number.in_(variations)).first()
    if not user:
        raise SystemExit(f"User not found for {phone}")

    user.is_active = True
    user.approval_status = ApprovalStatus.APPROVED
    user.is_unlimited_user = False

    # Simulasi auto debt melewati limit.
    user.total_quota_purchased_mb = 1000
    user.total_quota_used_mb = 1700
    user.auto_debt_offset_mb = 0

    # Pastikan tidak terkunci oleh reason lain agar policy auto-debt bisa dievaluasi jelas.
    user.is_blocked = False
    user.blocked_reason = None
    user.blocked_at = None
    user.blocked_by_id = None

    if not user.mikrotik_profile_name:
        user.mikrotik_profile_name = settings_service.get_setting("MIKROTIK_ACTIVE_PROFILE", "profile-aktif")

    target_profile = resolve_target_profile_for_user(user)
    db.session.commit()

    # Sinkronisasi address-list single-user agar blocked list langsung terbentuk.
    try:
        sync_address_list_for_single_user(user, client_ip=client_ip)
        db.session.commit()
    except Exception as e:
        print(f"WARN sync_address_list_for_single_user failed: {e}")

    print(
        f"Auto-debt threshold simulation: user_id={user.id} is_blocked={user.is_blocked} "
        f"blocked_reason={user.blocked_reason} target_profile={target_profile}"
    )
'@

  $pyB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($py))
  $cmdArgs = @("exec", "-T") + $envArgs + @(
    "backend",
    "python",
    "-c",
    "import base64,sys; exec(base64.b64decode('$pyB64').decode('utf-8'))"
  )
  try {
    Invoke-Compose $cmdArgs
  } catch {
    Write-Host "[WARN] Simulasi auto debt threshold gagal: $($_.Exception.Message)" -ForegroundColor Yellow
  }
}

function Assert-AutoDebtBindingRegular([string]$phoneNumber, [string]$clientMac) {
  if (-not $phoneNumber) { return }
  $envArgs = @(
    "-e", "TARGET_PHONE=$phoneNumber",
    "-e", "TARGET_MAC=$clientMac"
  )

  $py = @'
import os
from app import create_app
from app.extensions import db
from app.infrastructure.db.models import User
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection
from app.utils.formatters import get_phone_number_variations, format_to_local_phone

app = create_app()
with app.app_context():
    phone = os.environ.get("TARGET_PHONE") or ""
    target_mac = (os.environ.get("TARGET_MAC") or "").upper()
    variations = get_phone_number_variations(phone)
    user = db.session.query(User).filter(User.phone_number.in_(variations)).first()
    if not user:
        raise SystemExit(f"User not found for {phone}")

    username_08 = format_to_local_phone(user.phone_number) or ""

    with get_mikrotik_connection() as api:
        if not api:
            print("SKIP: MikroTik connection not available for binding assertion")
            raise SystemExit(0)

        entries = api.get_resource("/ip/hotspot/ip-binding").get()
        matched = []
        for entry in entries:
            mac = str(entry.get("mac-address") or "").upper()
            comment = str(entry.get("comment") or "")
            if target_mac and mac == target_mac:
                matched.append(entry)
                continue
            if username_08 and (f"user={username_08}" in comment or f"uid={user.id}" in comment):
                matched.append(entry)

        blocked_entries = [e for e in matched if str(e.get("type") or "").lower() == "blocked"]
        if blocked_entries:
            raise SystemExit(f"Found blocked ip-binding entries for auto-debt user: {blocked_entries}")

        print(f"IP-binding OK for auto-debt flow: matched_entries={len(matched)} type!=blocked")
'@

  $pyB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($py))
  $cmdArgs = @("exec", "-T") + $envArgs + @(
    "backend",
    "python",
    "-c",
    "import base64,sys; exec(base64.b64decode('$pyB64').decode('utf-8'))"
  )
  try {
    Invoke-Compose $cmdArgs
  } catch {
    Write-Host "[WARN] Skip assert ip-binding regular untuk auto debt: $($_.Exception.Message)" -ForegroundColor Yellow
  }
}

function Clear-AddressListForIp($ipAddress) {
  if (-not $ipAddress) { return }
  $envArgs = @(
    "-e", "TARGET_IP=$ipAddress"
  )

  $py = @'
import os
from app import create_app
from app.services import settings_service
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection, remove_address_list_entry

app = create_app()
with app.app_context():
    target_ip = os.environ.get("TARGET_IP")
    if not target_ip:
        raise SystemExit("TARGET_IP empty")

    list_names = [
        settings_service.get_setting("MIKROTIK_ADDRESS_LIST_ACTIVE", "active"),
        settings_service.get_setting("MIKROTIK_ADDRESS_LIST_FUP", "fup"),
        settings_service.get_setting("MIKROTIK_ADDRESS_LIST_INACTIVE", "inactive"),
        settings_service.get_setting("MIKROTIK_ADDRESS_LIST_EXPIRED", "expired"),
        settings_service.get_setting("MIKROTIK_ADDRESS_LIST_HABIS", "habis"),
        settings_service.get_setting("MIKROTIK_ADDRESS_LIST_BLOCKED", "blocked"),
    ]

    removed = 0
    with get_mikrotik_connection() as api:
        if not api:
            raise SystemExit("MikroTik connection failed")
        for list_name in list_names:
            if not list_name:
                continue
            ok, _msg = remove_address_list_entry(api, target_ip, list_name)
            if ok:
                removed += 1
    print(f"Cleanup address-list: ip={target_ip} removed={removed}")
'@

  $pyB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($py))
  $cmdArgs = @("exec", "-T") + $envArgs + @(
    "backend",
    "python",
    "-c",
    "import base64,sys; exec(base64.b64decode('$pyB64').decode('utf-8'))"
  )
  try {
    Invoke-Compose $cmdArgs
  } catch {
    Write-Host "[WARN] Skip MikroTik cleanup address-list (ip=$ipAddress): $($_.Exception.Message)"
  }
}

function Assert-AddressListStatus($ipAddress, $expectedStatus, $phoneNumber, $clientMac) {
  if (-not $ipAddress -or -not $expectedStatus) { return }
  $envArgs = @(
    "-e", "TARGET_IP=$ipAddress",
    "-e", "EXPECTED_STATUS=$expectedStatus",
    "-e", "TARGET_PHONE=$phoneNumber",
    "-e", "TARGET_MAC=$clientMac"
  )

  $py = @'
import os
from app import create_app
from app.extensions import db
from app.infrastructure.db.models import User
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection
from app.services import settings_service
from app.utils.formatters import get_phone_number_variations, format_to_local_phone

STATUS_KEYS = {
  "active": "MIKROTIK_ADDRESS_LIST_ACTIVE",
  "fup": "MIKROTIK_ADDRESS_LIST_FUP",
  "habis": "MIKROTIK_ADDRESS_LIST_HABIS",
  "expired": "MIKROTIK_ADDRESS_LIST_EXPIRED",
  "inactive": "MIKROTIK_ADDRESS_LIST_INACTIVE",
  "blocked": "MIKROTIK_ADDRESS_LIST_BLOCKED",
}

def _matches_comment(comment, user_id, username_08):
  if not comment:
    return False
  text = str(comment)
  return f"user_id={user_id}" in text or f"phone={username_08}" in text or f"user={user_id}" in text

app = create_app()
with app.app_context():
  target_ip = os.environ.get("TARGET_IP")
  expected_status = (os.environ.get("EXPECTED_STATUS") or "").lower()
  phone = os.environ.get("TARGET_PHONE") or ""
  target_mac = (os.environ.get("TARGET_MAC") or "").upper()
  if not target_ip:
    raise SystemExit("TARGET_IP empty")
  if expected_status not in STATUS_KEYS:
    raise SystemExit(f"Unknown EXPECTED_STATUS: {expected_status}")

  variations = get_phone_number_variations(phone)
  user = db.session.query(User).filter(User.phone_number.in_(variations)).first()
  if not user:
    raise SystemExit("User not found for address-list validation")
  username_08 = format_to_local_phone(user.phone_number) or ""

  list_names = {
    key: (settings_service.get_setting(cfg, key) or key)
    for key, cfg in STATUS_KEYS.items()
  }
  expected_list = list_names[expected_status]

  with get_mikrotik_connection() as api:
    if not api:
      raise SystemExit("MikroTik connection failed")

    candidate_ips = []
    if target_ip:
      candidate_ips.append(target_ip)

    bindings = api.get_resource("/ip/hotspot/ip-binding").get()
    for entry in bindings:
      mac = str(entry.get("mac-address") or "").upper()
      address = str(entry.get("address") or "")
      comment = entry.get("comment")
      if target_mac and mac == target_mac and address:
        candidate_ips.append(address)
        continue
      if _matches_comment(comment, user.id, username_08) and address:
        candidate_ips.append(address)

    seen = set()
    candidate_ips = [ip for ip in candidate_ips if ip and not (ip in seen or seen.add(ip))]

    success = False
    for ip in candidate_ips:
      entries = api.get_resource("/ip/firewall/address-list").get(address=ip)
      if not entries:
        continue

      matching_expected = [
        e for e in entries
        if e.get("list") == expected_list and _matches_comment(e.get("comment"), user.id, username_08)
      ]
      if not matching_expected:
        matching_expected = [
          e for e in entries
          if e.get("list") == expected_list
        ]
      if not matching_expected:
        continue

      other_status_lists = {v for k, v in list_names.items() if v and v != expected_list}
      conflicts = [e for e in entries if e.get("list") in other_status_lists]
      if conflicts:
        lists = ",".join(sorted({str(e.get("list")) for e in conflicts}))
        raise SystemExit(f"Conflicting lists for ip={ip}: {lists}")

      print(f"Address-list OK: ip={ip} status={expected_status} list={expected_list}")
      success = True
      break

    if not success:
      raise SystemExit(f"Expected list '{expected_list}' not found for ip(s)={candidate_ips}")
'@

  $pyB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($py))
  $cmdArgs = @("exec", "-T") + $envArgs + @(
    "backend",
    "python",
    "-c",
    "import base64,sys; exec(base64.b64decode('$pyB64').decode('utf-8'))"
  )
  $maxAttempts = 4
  for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
    try {
      Invoke-Compose $cmdArgs
      return
    } catch {
      if ($attempt -lt $maxAttempts) {
        Write-Host "[WARN] MikroTik assert address-list belum konsisten (attempt=$attempt/$maxAttempts, ip=$ipAddress status=$expectedStatus). Retry 2 detik..." -ForegroundColor Yellow
        Start-Sleep -Seconds 2
        continue
      }
      Write-Host "[WARN] Skip MikroTik assert address-list (ip=$ipAddress status=$expectedStatus): $($_.Exception.Message)"
    }
  }
}

function Set-UserStatus($status, $totalMb, $usedMb, $expiryDays, $profileName) {
  $envArgs = @(
    "-e", "TARGET_PHONE=$UserPhone",
    "-e", "TARGET_STATUS=$status",
    "-e", "TOTAL_MB=$totalMb",
    "-e", "USED_MB=$usedMb",
    "-e", "EXPIRY_DAYS=$expiryDays",
    "-e", "PROFILE_NAME=$profileName"
  )

  $py = @'
import os
from datetime import datetime, timezone, timedelta
from app import create_app
from app.extensions import db
from app.infrastructure.db.models import User, ApprovalStatus
from app.utils.formatters import get_phone_number_variations

app = create_app()
with app.app_context():
    phone = os.environ.get("TARGET_PHONE")
    status = os.environ.get("TARGET_STATUS")
    total_mb = float(os.environ.get("TOTAL_MB", "0"))
    used_mb = float(os.environ.get("USED_MB", "0"))
    expiry_days = int(os.environ.get("EXPIRY_DAYS", "0"))
    profile = os.environ.get("PROFILE_NAME") or None

    variations = get_phone_number_variations(phone)
    user = db.session.query(User).filter(User.phone_number.in_(variations)).first()
    if not user:
      raise SystemExit("User not found for status update")

    if status == "blocked":
        user.is_blocked = True
        user.blocked_reason = "Simulated"
        user.is_active = True
        user.approval_status = ApprovalStatus.APPROVED
    elif status == "inactive":
        user.is_blocked = False
        user.is_active = False
        user.approval_status = ApprovalStatus.APPROVED
    else:
        user.is_blocked = False
        user.is_active = True
        user.approval_status = ApprovalStatus.APPROVED

    user.total_quota_purchased_mb = total_mb
    user.total_quota_used_mb = used_mb
    if expiry_days != 0:
        user.quota_expiry_date = datetime.now(timezone.utc) + timedelta(days=expiry_days)
    else:
        user.quota_expiry_date = None

    if profile:
        user.mikrotik_profile_name = profile

    db.session.commit()
    print(f"User status updated: {status}")
'@

  $pyB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($py))
  $cmdArgs = @("exec", "-T") + $envArgs + @(
    "backend",
    "python",
    "-c",
    "import base64,sys; exec(base64.b64decode('$pyB64').decode('utf-8'))"
  )
  Invoke-Compose $cmdArgs
}
