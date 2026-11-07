package main

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"math/big"
	"os"
	"path/filepath"
	"syscall"
	"testing"
	"time"
)

func testCertificate(t *testing.T, name string) []byte {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil { t.Fatal(err) }
	certificate := &x509.Certificate{SerialNumber: big.NewInt(1),
		Subject: pkix.Name{CommonName: name}, NotBefore: time.Unix(0, 0),
		NotAfter: time.Unix(2000000000, 0), IsCA: true, BasicConstraintsValid: true}
	der, err := x509.CreateCertificate(rand.Reader, certificate, certificate, &key.PublicKey, key)
	if err != nil { t.Fatal(err) }
	return pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})
}

func TestFilterPreservesUnrelatedBytes(t *testing.T) {
	good := testCertificate(t, "emSign ECC Root CA - G3 extra")
	otherPEM := []byte("-----BEGIN PUBLIC KEY-----\nYWJj\n-----END PUBLIC KEY-----\n")
	prefix, middle, suffix := []byte("# initial comment\r\n"), []byte("\n# between\n"), []byte("trailing text\r\n")
	input := bytes.Join([][]byte{prefix, testCertificate(t, "emSign ECC Root CA - G3"), middle, good, otherPEM, testCertificate(t, "AAA Certificate Services"), suffix}, nil)
	want := bytes.Join([][]byte{prefix, middle, good, otherPEM, suffix}, nil)
	got, removed, err := filterPEM(input)
	if err != nil || removed != 2 || !bytes.Equal(got, want) { t.Fatalf("removed=%d error=%v; preservation=%v", removed, err, bytes.Equal(got, want)) }
}

func TestEmptyBinaryAndMalformed(t *testing.T) {
	for _, input := range [][]byte{nil, {}, []byte("\x00\xfe\xedbinary Java store")} {
		got, n, err := filterPEM(input)
		if err != nil || n != 0 || !bytes.Equal(got, input) { t.Fatalf("unmodified input changed: %v", err) }
	}
	for _, input := range [][]byte{[]byte("-----BEGIN CERTIFICATE-----\nbroken"), pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: []byte("invalid DER")})} {
		if _, _, err := filterPEM(input); err == nil { t.Fatal("malformed certificate accepted") }
	}
}

func negativeSerialCertificate(t *testing.T, name string) []byte {
	t.Helper()
	block, _ := pem.Decode(testCertificate(t, name))
	// Generated fixtures use serial 1 and explicit version 3. Changing INTEGER 1
	// to INTEGER -1 leaves DER structure and the subject intact; ParseCertificate
	// does not verify the signature (neither does the filtering helper).
	serial := bytes.Index(block.Bytes, []byte{0x02, 0x01, 0x01})
	if serial < 0 { t.Fatal("fixture serial INTEGER not found") }
	block.Bytes[serial+2] = 0xff
	return pem.EncodeToMemory(block)
}

func TestLegacyNegativeSerialPreservedAndTargetsRemoved(t *testing.T) {
	t.Setenv("GODEBUG", "x509negativeserial=0,http2client=0")
	previous := os.Getenv("GODEBUG")
	legacy := negativeSerialCertificate(t, "Legacy unrelated public root")
	block, _ := pem.Decode(legacy)
	if _, err := x509.ParseCertificate(block.Bytes); err == nil || err.Error() != "x509: negative serial number" {
		t.Fatalf("fixture must exercise negative-serial compatibility: %v", err)
	}
	prefix, suffix := []byte("# original legacy trust\r\n"), []byte("\n# retained comment\n")
	input := bytes.Join([][]byte{prefix, legacy, negativeSerialCertificate(t, "emSign ECC Root CA - G3"), testCertificate(t, "AAA Certificate Services"), suffix}, nil)
	want := bytes.Join([][]byte{prefix, legacy, suffix}, nil)
	got, removed, err := filterPEM(input)
	if err != nil || removed != 2 || !bytes.Equal(got, want) {
		t.Fatalf("legacy filtering: removed=%d preservation=%v error=%v", removed, bytes.Equal(got, want), err)
	}
	if os.Getenv("GODEBUG") != previous { t.Fatal("compatibility setting leaked") }
	// An additional structural error must still fail; compatibility is not an
	// instruction to preserve every certificate that x509 cannot parse.
	malformed := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: block.Bytes[:len(block.Bytes)-1]})
	if _, _, err := filterPEM(malformed); err == nil { t.Fatal("malformed legacy certificate accepted") }
	if os.Getenv("GODEBUG") != previous { t.Fatal("setting changed after malformed certificate") }
}

func TestStoresSymlinksAndMetadata(t *testing.T) {
	dir := t.TempDir()
	standalone, bundle := filepath.Join(dir, "target.crt"), filepath.Join(dir, "bundle.crt")
	good := testCertificate(t, "Good public root")
	target := testCertificate(t, "AAA Certificate Services")
	if err := os.WriteFile(standalone, target, 0644); err != nil { t.Fatal(err) }
	if err := os.WriteFile(bundle, append(append([]byte{}, target...), good...), 0640); err != nil { t.Fatal(err) }
	for name, destination := range map[string]string{"1234.0": standalone, "bundle-link.pem": bundle, "dangling.0": filepath.Join(dir, "absent")} {
		if err := os.Symlink(destination, filepath.Join(dir, name)); err != nil { t.Fatal(err) }
	}
	outside := filepath.Join(t.TempDir(), "outside.pem")
	if err := os.WriteFile(outside, target, 0600); err != nil { t.Fatal(err) }
	if err := os.Symlink(outside, filepath.Join(dir, "outside-link")); err != nil { t.Fatal(err) }
	before, _ := os.Stat(bundle)
	changes, n, err := planChanges([]string{dir})
	if err != nil || n != 4 { t.Fatalf("plan: occurrences=%d error=%v", n, err) }
	if err := applyChanges(changes); err != nil { t.Fatal(err) }
	for _, name := range []string{standalone, filepath.Join(dir, "1234.0")} {
		if _, err := os.Lstat(name); !os.IsNotExist(err) { t.Fatalf("target remains: %s", name) }
	}
	after, _ := os.Stat(bundle)
	if !os.SameFile(before, after) || before.Mode() != after.Mode() { t.Fatal("inode or mode changed") }
	oldStat, newStat := before.Sys().(*syscall.Stat_t), after.Sys().(*syscall.Stat_t)
	if oldStat.Uid != newStat.Uid || oldStat.Gid != newStat.Gid { t.Fatal("ownership changed") }
	actual, _ := os.ReadFile(bundle)
	if !bytes.Equal(actual, good) { t.Fatal("good root changed") }
	if link, err := os.Readlink(filepath.Join(dir, "bundle-link.pem")); err != nil || link != bundle { t.Fatal("bundle symlink changed") }
	actual, _ = os.ReadFile(outside)
	if !bytes.Equal(actual, target) { t.Fatal("out-of-scope symlink target changed") }
}

func TestPlanFailsBeforeMutation(t *testing.T) {
	dir := t.TempDir()
	valid := filepath.Join(dir, "a.crt")
	data := testCertificate(t, "emSign ECC Root CA - G3")
	if err := os.WriteFile(valid, data, 0644); err != nil { t.Fatal(err) }
	if err := os.WriteFile(filepath.Join(dir, "z.crt"), []byte("-----BEGIN CERTIFICATE-----\nmalformed"), 0644); err != nil { t.Fatal(err) }
	if _, _, err := planChanges([]string{dir}); err == nil { t.Fatal("malformed store accepted") }
	actual, _ := os.ReadFile(valid)
	if !bytes.Equal(actual, data) { t.Fatal("planning mutated file") }
}
