// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors

// The lock files pin the plugins' dependencies too.
buildscript {
    configurations.classpath {
        resolutionStrategy.activateDependencyLocking()
    }
}

// Plugins are declared here once and applied in the modules that need them.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.kotlin.compose) apply false
}

allprojects {
    dependencyLocking {
        lockAllConfigurations()
        // Gradle writes this one to the lock, then fails the next build because
        // that build does not resolve it.
        ignoredDependencies.add("org.jetbrains.kotlin:kotlin-stdlib-common")
    }
}
