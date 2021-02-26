!define registerExtension "!insertmacro registerExtension"
!define unregisterExtension "!insertmacro unregisterExtension"
!define SHCNE_ASSOCCHANGED 0x8000000
!define SHCNF_IDLIST 0

; Source = http://nsis.sourceforge.net/File_Association
; Patched for SABnzbd by swi-tch

!macro registerExtension icon executable extension description
       Push "${icon}"  ; "full path to icon.ico"
       Push "${executable}"  ; "full path to my.exe"
       Push "${extension}"   ;  ".mkv"
       Push "${description}" ;  "MKV File"
       Call registerExtension
!macroend

; back up old value of .opt
Function registerExtension
!define Index "Line${__LINE__}"
  pop $R0 ; ext name
  pop $R1
  pop $R2
  pop $R3
  push $1
  push $0
  DeleteRegKey HKEY_CURRENT_USER "Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\$R1"
  WriteRegStr HKCR $R1 "" $R0
	WriteRegStr HKCR $R0 "" $R0
	WriteRegStr HKCR "$R0\shell" "" "open"
	WriteRegStr HKCR "$R0\DefaultIcon" "" "$R3,0"
  WriteRegStr HKCR "$R0\shell\open\command" "" '"$R2" "%1"'
  WriteRegStr HKCR "$R0\shell\edit" "" "Edit $R0"
  WriteRegStr HKCR "$R0\shell\edit\command" "" '"$R2" "%1"'
  pop $0
  pop $1
!undef Index
System::Call 'Shell32::SHChangeNotify(i ${SHCNE_ASSOCCHANGED}, i ${SHCNF_IDLIST}, i 0, i 0)'
FunctionEnd

!macro unregisterExtension extension description
       Push "${extension}"   ;  ".mkv"
       Push "${description}"   ;  "MKV File"
       Call un.unregisterExtension
!macroend

Function un.unregisterExtension
  pop $R1 ; description
  pop $R0 ; extension
!define Index "Line${__LINE__}"
  DeleteRegKey HKCR $R0
!undef Index
System::Call 'Shell32::SHChangeNotify(i ${SHCNE_ASSOCCHANGED}, i ${SHCNF_IDLIST}, i 0, i 0)'
FunctionEnd