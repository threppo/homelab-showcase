// filter-roots removes the two incident-related public roots from OS PEM stores.
// Build with CGO_ENABLED=0; no shell or external commands are required.
package main

import (
	"bytes"
	"crypto/x509"
	"encoding/pem"
	"errors"
	"flag"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

var publicStores = []string{
	"/etc/ssl/certs", "/usr/share/ca-certificates/mozilla",
	"/etc/ssl/cert.pem", "/etc/pki/tls/certs",
	"/etc/pki/ca-trust/extracted/pem",
}

type change struct {
	path string
	data []byte
	remove bool
}

// certificateCommonName keeps x509's full DER parsing. Some legacy public roots
// have negative serial numbers, accepted by Go before 1.23. Retry only that exact
// error using Go's documented compatibility switch, scoped to this parse and
// restored immediately. This offline helper never verifies TLS or signatures;
// the switch does not enter the resulting image environment. Other parse errors
// still abort, and the original certificate bytes are never modified.
func certificateCommonName(der []byte) (string, error) {
	certificate, err := x509.ParseCertificate(der)
	if err != nil && err.Error() == "x509: negative serial number" {
		previous, present := os.LookupEnv("GODEBUG")
		if setErr := os.Setenv("GODEBUG", previous+",x509negativeserial=1"); setErr != nil {
			return "", setErr
		}
		certificate, err = x509.ParseCertificate(der)
		var restoreErr error
		if present {
			restoreErr = os.Setenv("GODEBUG", previous)
		} else {
			restoreErr = os.Unsetenv("GODEBUG")
		}
		if restoreErr != nil { return "", restoreErr }
	}
	if err != nil { return "", err }
	return certificate.Subject.CommonName, nil
}

// filterPEM preserves every byte outside the removed certificate blocks. Unlike
// pem.Decode on an entire bundle, it does not discard preceding comments/text.
func filterPEM(data []byte) ([]byte, int, error) {
	begin := []byte("-----BEGIN CERTIFICATE-----")
	end := []byte("-----END CERTIFICATE-----")
	var result []byte
	removed := 0
	for len(data) > 0 {
		start := bytes.Index(data, begin)
		if start < 0 {
			result = append(result, data...)
			break
		}
		result = append(result, data[:start]...)
		data = data[start:]
		finish := bytes.Index(data, end)
		if finish < 0 {
			return nil, 0, errors.New("unterminated CERTIFICATE PEM")
		}
		finish += len(end)
		if len(data) > finish && data[finish] == '\r' {
			finish++
		}
		if len(data) > finish && data[finish] == '\n' {
			finish++
		}
		encoded := data[:finish]
		block, rest := pem.Decode(encoded)
		if block == nil || block.Type != "CERTIFICATE" || len(bytes.TrimSpace(rest)) != 0 {
			return nil, 0, errors.New("malformed CERTIFICATE PEM")
		}
		commonName, err := certificateCommonName(block.Bytes)
		if err != nil {
			return nil, 0, fmt.Errorf("invalid certificate DER: %w", err)
		}
		switch commonName {
		case "emSign ECC Root CA - G3", "AAA Certificate Services":
			removed++
		default:
			result = append(result, encoded...)
		}
		data = data[finish:]
	}
	return result, removed, nil
}

func insideStores(path string, roots []string) bool {
	for _, root := range roots {
		if path == root || strings.HasPrefix(path, root+string(os.PathSeparator)) {
			return true
		}
	}
	return false
}

// Plan every modification before changing files, so a malformed certificate in
// any selected store aborts the build without partially filtering other stores.
func planChanges(roots []string) ([]change, int, error) {
	paths := make(map[string]bool)
	for _, root := range roots {
		err := filepath.WalkDir(root, func(path string, entry fs.DirEntry, err error) error {
			if errors.Is(err, fs.ErrNotExist) { return nil }
			if err != nil { return err }
			if !entry.IsDir() { paths[path] = true }
			return nil
		})
		if err != nil { return nil, 0, err }
	}
	ordered := make([]string, 0, len(paths))
	for path := range paths { ordered = append(ordered, path) }
	sort.Strings(ordered)
	var changes []change
	count := 0
	for _, path := range ordered {
		info, err := os.Stat(path) // Follow certificate symlinks, not directories.
		if errors.Is(err, fs.ErrNotExist) { continue }
		if err != nil { return nil, 0, err }
		if !info.Mode().IsRegular() { continue }
		resolved, err := filepath.EvalSymlinks(path)
		if err != nil { return nil, 0, err }
		// Never follow a trust-store link into an unrelated application/key path.
		if !insideStores(resolved, roots) { continue }
		data, err := os.ReadFile(path)
		if err != nil { return nil, 0, err }
		filtered, removed, err := filterPEM(data)
		if err != nil { return nil, 0, fmt.Errorf("%s: %w", path, err) }
		if removed == 0 { continue } // Includes binary Java stores and empty files.
		count += removed
		changes = append(changes, change{path: path, data: filtered,
			remove: len(bytes.TrimSpace(filtered)) == 0})
	}
	return changes, count, nil
}

func applyChanges(changes []change) error {
	// Rewrite mixed bundles first, before deleting standalone certificates. Open
	// without O_TRUNC to preserve ownership, mode, inode and the original symlink.
	for _, item := range changes {
		if item.remove { continue }
		file, err := os.OpenFile(item.path, os.O_WRONLY, 0)
		if err != nil { return err }
		_, err = file.WriteAt(item.data, 0)
		if err == nil { err = file.Truncate(int64(len(item.data))) }
		if err == nil { err = file.Sync() }
		closeErr := file.Close()
		if err != nil { return err }
		if closeErr != nil { return closeErr }
		fmt.Printf("public-ca-filtered\t%s\n", item.path)
	}
	for _, item := range changes {
		if !item.remove { continue }
		if err := os.Remove(item.path); err != nil { return err }
		fmt.Printf("public-ca-removed\t%s\n", item.path)
	}
	return nil
}

func main() {
	keep := flag.Bool("keep-binary", false, "retain this helper after successful filtering")
	flag.Parse()
	if flag.NArg() != 0 {
		fmt.Fprintln(os.Stderr, "unexpected arguments; trust-store paths are fixed")
		os.Exit(1)
	}
	changes, removed, err := planChanges(publicStores)
	if err == nil { err = applyChanges(changes) }
	if err == nil && !*keep {
		var executable string
		executable, err = os.Executable()
		if err == nil { err = os.Remove(executable) }
	}
	if err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
	fmt.Printf("public-ca-filter-complete\tpaths=%d\tcertificate-occurrences=%d\n", len(changes), removed)
}
