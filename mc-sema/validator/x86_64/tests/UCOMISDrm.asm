BITS 64
;TEST_FILE_META_BEGIN
;TEST_TYPE=TEST_F
;TEST_IGNOREFLAGS=
;TEST_FILE_META_END

; put 2 into ecx for future load into xmm0
mov ecx, 2
cvtsi2sd xmm0, ecx
mov ecx, 0
cvtsi2sd xmm1, ecx
;TEST_BEGIN_RECORDING
lea rcx, [rsp-8]
movsd [rcx], xmm1
ucomiss xmm0, [rcx]
mov ecx, 0
;TEST_END_RECORDING
cvtsi2sd xmm0, ecx
cvtsi2sd xmm1, ecx
