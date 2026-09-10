// wifi_flash_port.cpp -- see wifi_flash_port.h. The one translation
// unit this ticket adds that reaches pxt.h: everything else in the
// credential-store feature (WifiCredentialStore, WifiFlashPort's
// abstract interface) is host-portable.
//
// Flash is memory-mapped on this chip, so a READ is a plain copy from
// the address -- codal::MicroBitFlash offers no read method because it
// doesn't need one. A WRITE goes through
// codal::MicroBitFlash::flash_write(), which does the "does this need
// an erase first" check and, if so, the erase-preserve-rewrite dance
// against its own default scratch page (MICROBIT_DEFAULT_SCRATCH_PAGE)
// generically -- this file never calls NRF52FlashManager directly,
// which is the raw path that assumes no erase is needed and would
// silently corrupt a slot that needed one.
#include "wifi_flash_port.h"

#include "pxt.h"

#include "MicroBitFlash.h"

namespace diffDrive {

namespace {
// Function-local static, same reasoning as MicroBitI2CBus
// (microbit_i2c_bus.cpp) and defaultI2CBus(): constructed on first use,
// after CODAL's own static init, never destroyed.
codal::MicroBitFlash& flashDriver() {
  static codal::MicroBitFlash flash;
  return flash;
}

// True iff [offset, offset+length) fits inside the page this seam
// promises -- the "degrade safely" guard wifi_flash_port.h's header
// comment and this ticket's own critical context both require: an
// out-of-range request is refused, not a wild flash access.
bool inRange(uint32_t offset, uint32_t length) {
  if (length == 0) return true;
  if (offset >= WifiFlashPort::kPageBytes) return false;
  return length <= WifiFlashPort::kPageBytes - offset;
}
}  // namespace

void WifiFlashPortCodal::read(uint32_t offset, uint8_t* buffer, uint32_t length) const {
  if (!inRange(offset, length) || length == 0) return;
  const uint8_t* src = reinterpret_cast<const uint8_t*>(kFlashPageAddress + offset);
  for (uint32_t i = 0; i < length; ++i) buffer[i] = src[i];
}

bool WifiFlashPortCodal::write(uint32_t offset, const uint8_t* buffer, uint32_t length) {
  if (!inRange(offset, length)) return false;
  if (length == 0) return true;
  void* address = reinterpret_cast<void*>(kFlashPageAddress + offset);
  // flash_write()'s buffer parameter is non-const in the vendored
  // signature; it is only ever read from, per its own header comment.
  void* source = const_cast<void*>(reinterpret_cast<const void*>(buffer));
  // scratch_addr left at its default (NULL -> MICROBIT_DEFAULT_SCRATCH_PAGE)
  // deliberately: that page is already the flash driver's own scratch
  // for every other flash_write() caller on this build, so this store
  // adds no second scratch consumer.
  return flashDriver().flash_write(address, source, static_cast<int>(length)) != 0;
}

bool WifiFlashPortCodal::erasePage() {
  flashDriver().erase_page(reinterpret_cast<uint32_t*>(kFlashPageAddress));
  return true;
}

}  // namespace diffDrive
