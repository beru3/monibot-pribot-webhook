
# コピー元のファイル
$sourceFile = "01.mp3"

# 保存先フォルダ
$outputFolder = "UserTones"
if (!(Test-Path -Path $outputFolder)) {
    New-Item -ItemType Directory -Path $outputFolder
}

# メンバー名リスト
$members = @("backlog", "seitaro_abe", "rpa-sales", "r_mishima", "y_nakata", "y_ito", "coo", "akihiro_furuie", "m_sakaguchi", "ak_otake", "s_ootani", "tominaga", "t_kobori", "r_yamamoto", "k_shimazaki", "f_soda", "k_toi", "kuwabara", "k_yokokawa", "s_tsumura", "h_tate", "ceo", "executive", "k_fujioka", "e_namekata", "s_fukuyama", "to_suzuki", "h_nagashima", "m_abe", "s_takagi", "h_takahashi", "n_saito")

# ファイルをコピーして名前を変更
foreach ($member in $members) {
    # 新しいファイル名
    $newFileName = "$member.mp3"
    # 保存先パス
    $destinationFile = Join-Path -Path $outputFolder -ChildPath $newFileName
    # コピー処理
    Copy-Item -Path $sourceFile -Destination $destinationFile
    Write-Host "Copied: $sourceFile -> $destinationFile"
}

Write-Host "complete"
